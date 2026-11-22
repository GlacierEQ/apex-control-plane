"""Real subprocess -> durable inspector -> scheduler reconciliation boundaries."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "control_plane.py"
sys.path.insert(0, str(ROOT / "src"))

from continuous_control_plane import (
    ContinuousControlPlane, ControlEvent, JsonlControlStore,
    WorkState, load_continuous_control_config,
)


def queued(tmp_path):
    store = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    plane = ContinuousControlPlane.from_config(JsonlControlStore(store), config)
    item = plane.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="mission-inspector", correlation_id="corr-inspector",
        payload={"test": "real-subprocess-inspection"},
    ))[0]
    return store, config, item


def invoke(store, capability, receipt_path, command, *, verification=None):
    args = [sys.executable, str(CLI), "--run-next-local", str(store), capability]
    if verification is not None:
        args.extend(["--verify-file", str(verification)])
    args.extend(["--inspect-execution-receipt", str(receipt_path), "--", *map(str, command)])
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=20)


def recovered(store, config, item):
    plane = ContinuousControlPlane.from_config(JsonlControlStore(store), config)
    assert plane.work[item.work_id].state is WorkState.RECONCILING
    assert plane.claim_next(worker_id="other", capabilities=[item.capability]) is None
    return plane


def test_real_pinned_capability_receipt_inspection_reconciles_without_false_success(tmp_path):
    store, config, item = queued(tmp_path)
    doc = tmp_path / "skills" / "agent" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Agent\n\nContext first; execute with durable receipts.\n")
    durable = tmp_path / "execution-receipt.json"
    nested = [
        sys.executable, str(CLI), "--exec-capability",
        "--skills-root", str(doc.parent.parent), "--select", "skill:agent",
        "--sha256", hashlib.sha256(doc.read_bytes()).hexdigest(),
        "--receipt-path", str(durable), "--",
        sys.executable, "-c", "import sys; sys.stdin.buffer.read(); print('real child ran')",
    ]
    result = invoke(store, item.capability, durable, nested)
    assert result.returncode == 5, (result.stdout, result.stderr)
    assert json.loads(result.stdout)["status"] == "unconfirmed"
    assert durable.exists()
    plane = recovered(store, config, item)
    receipts = list(plane.receipts.values())
    assert len(receipts) == 1
    details = receipts[0].details
    assert details["receipt_inspection"]["status"] == "inspected_unverified"
    assert details["outcome_evidence"] == "unattested_receipt"
    assert details["outcome_verified"] is False


def test_invalid_fresh_receipt_reconciles_and_survives_restart(tmp_path):
    store, config, item = queued(tmp_path)
    durable = tmp_path / "invalid.json"
    command = [sys.executable, "-c", "from pathlib import Path;import sys;Path(sys.argv[1]).write_text('{invalid json')", str(durable)]
    result = invoke(store, item.capability, durable, command)
    assert result.returncode == 5, (result.stdout, result.stderr)
    plane = recovered(store, config, item)
    assert len(plane.receipts) == 1
    assert next(iter(plane.receipts.values())).details["receipt_inspection"]["status"] == "inspection_failed"


def test_stale_receipt_cannot_launder_fresh_artifact_success(tmp_path):
    store, config, item = queued(tmp_path)
    durable = tmp_path / "old-receipt.json"
    durable.write_text(json.dumps({"status": "verified", "outcome_verified": True}))
    artifact = tmp_path / "fresh.txt"
    command = [
        sys.executable, "-c",
        "from pathlib import Path;import sys;Path(sys.argv[1]).write_text('produced')", str(artifact),
    ]
    result = invoke(store, item.capability, durable, command, verification=artifact)
    assert result.returncode == 5, (result.stdout, result.stderr)
    assert artifact.read_text() == "produced"
    plane = recovered(store, config, item)
    assert len(plane.receipts) == 1
    details = next(iter(plane.receipts.values())).details
    assert details["receipt_inspection"]["status"] == "inspection_failed"
    assert "not fresh" in details["receipt_inspection"]["reason"]
    assert not any(r.receipt_kind == "verification" for r in plane.receipts.values())


def test_local_queue_enforces_subprocess_deadline_and_reconciles(tmp_path):
    """A long-running real local command must not leave the scheduler hung."""
    import os
    store, config, item = queued(tmp_path)
    command = [
        sys.executable, str(CLI), "--run-next-local", str(store),
        item.capability, "--", sys.executable, "-c",
        "import time; time.sleep(1.5)",
    ]
    env = dict(os.environ, GLACIEREQ_LOCAL_COMMAND_TIMEOUT="0.2")
    result = subprocess.run(command, cwd=ROOT, capture_output=True,
                            text=True, env=env, timeout=7)
    assert result.returncode == 5, (result.stdout, result.stderr)
    assert json.loads(result.stdout)["status"] == "unconfirmed"
    plane = recovered(store, config, item)
    details = next(iter(plane.receipts.values())).details
    assert details["timed_out"] is True
    assert details["outcome_verified"] is False


def test_local_queue_stream_quota_failure_does_not_retry(tmp_path):
    """A noisy worker must not exhaust RAM/disk or be certified successful."""
    import os
    store, config, item = queued(tmp_path)
    command = [
        sys.executable, str(CLI), "--run-next-local", str(store),
        item.capability, "--", sys.executable, "-c",
        "import sys; sys.stdout.write('X'*2000000)",
    ]
    env = dict(os.environ, GLACIEREQ_LOCAL_COMMAND_TIMEOUT="6")
    result = subprocess.run(command, cwd=ROOT, capture_output=True,
                            text=True, env=env, timeout=12)
    assert result.returncode == 5, (result.stdout[:500], result.stderr)
    assert json.loads(result.stdout)["status"] == "unconfirmed"
    plane = recovered(store, config, item)
    details = next(iter(plane.receipts.values())).details
    assert details["output_quota_exhausted"] is True
    assert details["outcome_verified"] is False
    assert len(details["stdout"]) <= 65536


def test_local_queue_can_verify_multi_megabyte_artifact_without_output_quota_limit(tmp_path):
    """Worker artifact size is separate from stdout/stderr capture limits."""
    store, config, item = queued(tmp_path)
    artifact = tmp_path / "artifact.bin"
    command = [
        sys.executable, str(CLI), "--run-next-local", str(store),
        item.capability, "--verify-file", str(artifact), "--",
        sys.executable, "-c",
        "from pathlib import Path;import sys;Path(sys.argv[1]).write_bytes(b'Z'*4000000)",
        str(artifact),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True,
                            text=True, timeout=12)
    assert result.returncode == 0, (result.stdout[:500], result.stderr)
    plane = ContinuousControlPlane.from_config(JsonlControlStore(store), config)
    assert plane.work[item.work_id].state is WorkState.COMPLETE
    proof = next(r for r in plane.receipts.values() if r.receipt_kind == "verification")
    assert proof.details["bytes"] == 4000000
    assert proof.details["sha256"] == hashlib.sha256(b'Z' * 4000000).hexdigest()


def test_worker_receipt_malformed_shape_reconciles_without_crashing(tmp_path):
    """A bad worker adapter cannot bypass persistent state by crashing parsing."""
    from continuous_control_plane import ExecutionReceipt

    invalid_evidence = [
        ("verified", None),
        ("verified", []),
        ("verified", 7),
        ("verified", "nonmapping"),
        ([], {}),
        ({"claim": "verified"}, {}),
    ]
    for index, (status, details) in enumerate(invalid_evidence):
        scoped = tmp_path / str(index)
        scoped.mkdir()
        store, config, item = queued(scoped)
        def worker(work):
            return ExecutionReceipt(
                work_id=work.work_id, mission_id=work.mission_id,
                correlation_id=work.correlation_id,
                receipt_kind="verification", status=status,
                source_system="malformed-test", details=details,
            )
        plane = ContinuousControlPlane.from_config(JsonlControlStore(store), config)
        result = plane.execute_next_local(
            worker_id="isolated", capabilities=[item.capability], executor=worker,
        )
        assert result["status"] == "unconfirmed"
        after = recovered(store, config, item)
        assert not after.receipts


def test_worker_receipt_unhashable_or_nonjson_fields_reconcile(tmp_path):
    """Invalid IDs and non-JSON detail structures must fail before ledger writes."""
    from continuous_control_plane import ExecutionReceipt

    variants = (
        {"receipt_kind": ["verification"]},
        {"source_system": ["worker"]},
        {"provider_receipt_id": ["duplicate"]},
        {"details": {"unsafe": {1, 2}}},
    )
    for index, override in enumerate(variants):
        scoped = tmp_path / str(index)
        scoped.mkdir()
        store, config, item = queued(scoped)
        def worker(work):
            fields = dict(
                work_id=work.work_id, mission_id=work.mission_id,
                correlation_id=work.correlation_id, receipt_kind="verification",
                status="verified", source_system="agent", details={},
            )
            fields.update(override)
            return ExecutionReceipt(**fields)
        plane = ContinuousControlPlane.from_config(JsonlControlStore(store), config)
        result = plane.execute_next_local(
            worker_id="malformed", capabilities=[item.capability], executor=worker,
        )
        assert result["status"] == "unconfirmed"
        assert not recovered(store, config, item).receipts
