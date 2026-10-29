"""Executable APEX CLI behavior, not simulated success receipts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "control_plane.py"


def test_idle_control_plane_cannot_fabricate_completed_routes() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI)], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 3, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "idle"
    assert payload["mission_complete"] is False
    assert payload["routes_run"] == 0
    assert payload["executed"] is False


def test_control_plane_runs_real_local_command_and_reports_actual_exit(tmp_path: Path) -> None:
    target = tmp_path / "executed.txt"
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('actual execution')",
        str(target),
    ]
    result = subprocess.run(
        [sys.executable, str(CLI), "--exec", *command],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_text() == "actual execution"
    payload = json.loads(result.stdout)
    assert payload["status"] == "process_succeeded_unverified"
    assert payload["mission_complete"] is False
    assert payload["outcome_verified"] is False
    assert payload["executed"] is True
    assert payload["routes_run"] == 1
    assert payload["exit_code"] == 0


def test_control_plane_propagates_real_process_failure() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI), "--exec", sys.executable, "-c", "raise SystemExit(17)"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 17
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["exit_code"] == 17
    assert payload["executed"] is True


def test_cli_dequeues_real_work_and_runs_supplied_command(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        load_continuous_control_config, WorkState,
    )
    store_path = tmp_path / "queue"
    cp = ContinuousControlPlane.from_config(
        JsonlControlStore(store_path),
        load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json"),
    )
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="mission-test", correlation_id="corr-test", payload={},
    ))[0]
    target = tmp_path / "proof.txt"
    command = [sys.executable, "-c",
               "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')", str(target)]
    result = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--", *command],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 4, result.stderr
    assert target.read_text() == "ran"
    payload = json.loads(result.stdout)
    assert payload["executed"] is True
    assert payload["status"] == "awaiting_receipts"
    cp = ContinuousControlPlane.from_config(
        JsonlControlStore(store_path),
        load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json"),
    )
    assert cp.work[work.work_id].state is WorkState.VERIFYING


def test_cli_with_no_queued_local_work_is_idle_not_fabricated_success(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(tmp_path / "queue"),
         "case.response.ingest", "--", sys.executable, "-c", "print('not invoked')"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 3, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "idle"
    assert payload["executed"] is False



def test_cli_verified_artifact_closes_work_in_one_execution(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        WorkState, load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="proof-mission", correlation_id="correlated", payload={},
    ))[0]
    target = tmp_path / "real-output.txt"
    cmd = [sys.executable, "-c",
           "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('verified work')",
           str(target)]
    run = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--verify-file", str(target), "--", *cmd],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert run.returncode == 0, run.stderr
    assert target.read_text() == "verified work"
    payload = json.loads(run.stdout)
    assert payload["status"] == "complete"
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    assert cp.work[work.work_id].state is WorkState.COMPLETE
    assert {r.receipt_kind for r in cp.receipts.values()} == {"execution", "verification"}
    verified = next(r for r in cp.receipts.values() if r.receipt_kind == "verification")
    assert verified.details["bytes"] == len(target.read_bytes())
    assert len(verified.details["sha256"]) == 64


def test_cli_missing_artifact_does_not_claim_complete(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        WorkState, load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="missing-artifact", correlation_id="correlated", payload={},
    ))[0]
    missing = tmp_path / "never-created.txt"
    run = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--verify-file", str(missing), "--",
         sys.executable, "-c", "print('ran without artifact')"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert run.returncode == 4, run.stderr
    assert json.loads(run.stdout)["status"] == "awaiting_receipts"
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    assert cp.work[work.work_id].state is WorkState.VERIFYING
    assert {r.receipt_kind for r in cp.receipts.values()} == {"execution"}


def test_cli_preexisting_unchanged_artifact_is_not_current_run_proof(tmp_path: Path) -> None:
    """A successful no-op command must not promote a stale artifact to verified."""
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        WorkState, load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="stale-file", correlation_id="stale-corr", payload={},
    ))[0]
    target = tmp_path / "previous-run.txt"
    target.write_text("old output")
    result = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--verify-file", str(target), "--",
         sys.executable, "-c", "print('success without writing target')"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 4, result.stderr
    assert json.loads(result.stdout)["status"] == "awaiting_receipts"
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    assert cp.work[work.work_id].state is WorkState.VERIFYING
    assert {r.receipt_kind for r in cp.receipts.values()} == {"execution"}


def test_cli_rewritten_existing_artifact_can_verify_current_run(tmp_path: Path) -> None:
    """Legitimate rewrites of an existing output path retain same-run completion."""
    import os
    import time
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        WorkState, load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="rewrite-file", correlation_id="rewrite-corr", payload={},
    ))[0]
    target = tmp_path / "existing.txt"
    target.write_text("same bytes")
    prior = time.time() - 10
    os.utime(target, (prior, prior))
    result = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--verify-file", str(target), "--",
         sys.executable, "-c",
         "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('same bytes')",
         str(target)],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "complete"
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    assert cp.work[work.work_id].state is WorkState.COMPLETE


def test_cli_prior_verification_receipt_does_not_verify_later_unrelated_execution(tmp_path: Path) -> None:
    """Required kinds must be present in the current attempt, not merely historical."""
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, ExecutionReceipt,
        JsonlControlStore, WorkState, load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="stale-receipt", correlation_id="old-proof-corr", payload={},
    ))[0]
    cp.record_receipt(ExecutionReceipt(
        work_id=work.work_id, mission_id=work.mission_id,
        correlation_id=work.correlation_id, receipt_kind="verification",
        status="verified", source_system="old-run",
        details={"scope": "prior attempt only"},
    ))
    result = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--", sys.executable, "-c", "print('new no-op')"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 4, result.stderr
    assert json.loads(result.stdout)["status"] == "awaiting_receipts"
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    assert cp.work[work.work_id].state is WorkState.VERIFYING


def test_cli_symlink_target_is_not_accepted_as_artifact_readback(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        WorkState, load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="symlink-artifact", correlation_id="symlink-corr", payload={},
    ))[0]
    source = tmp_path / "source.txt"
    source.write_text("old secret-adjacent source")
    target = tmp_path / "link.txt"
    target.symlink_to(source)
    result = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--verify-file", str(target), "--",
         sys.executable, "-c", "print('no artifact generated')"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 4, result.stderr
    assert json.loads(result.stdout)["status"] == "awaiting_receipts"
    cp = ContinuousControlPlane.from_config(JsonlControlStore(store_path), config)
    assert cp.work[work.work_id].state is WorkState.VERIFYING


def test_queued_local_verified_file_proves_work_item_not_entire_mission(tmp_path: Path) -> None:
    """A true local success must still not claim full mission completion."""
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        load_continuous_control_config,
    )
    store_path = tmp_path / "queue"
    cp = ContinuousControlPlane.from_config(
        JsonlControlStore(store_path),
        load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json"),
    )
    work = cp.ingest_event(ControlEvent(
        event_type="gmail.reply.received", source_system="test",
        subject_id="truthful-completion", correlation_id="correct-correlation", payload={},
    ))[0]
    target = tmp_path / "fresh-evidence.txt"
    run = subprocess.run(
        [sys.executable, str(CLI), "--run-next-local", str(store_path),
         work.capability, "--verify-file", str(target), "--",
         sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).write_text('fresh')", str(target)],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert run.returncode == 0, run.stderr
    payload = json.loads(run.stdout)
    assert payload["status"] == "complete"
    assert payload["work_item_complete"] is True
    assert payload["mission_complete"] is False
    assert payload["outcome_scope"] == "local_work_item"


def test_cli_invalid_command_never_reports_success() -> None:
    run = subprocess.run(
        [sys.executable, str(CLI), "--not-a-command"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert run.returncode != 0
    assert json.loads(run.stdout)["mission_complete"] is False

def test_cli_drain_local_attempts_every_independent_work_and_verifies_all(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from continuous_control_plane import (
        ContinuousControlPlane, ControlEvent, JsonlControlStore,
        load_continuous_control_config, WorkState,
    )
    queue = tmp_path / "queue"
    config = load_continuous_control_config(ROOT / "config" / "continuous_control_plane.json")
    cp = ContinuousControlPlane.from_config(JsonlControlStore(queue), config)
    ids = []
    for n in (1, 2):
        work = cp.ingest_event(ControlEvent(
            event_type="gmail.reply.received", source_system="test",
            subject_id=f"mission-{n}", correlation_id=f"corr-{n}", payload={},
        ))[0]
        ids.append(work.work_id)
    target = tmp_path / "proof-growing.txt"
    result = subprocess.run(
        [sys.executable, str(CLI), "--drain-local", str(queue),
         work.capability, "--verify-file", str(target), "--",
         sys.executable, "-c",
         "from pathlib import Path; import sys; Path(sys.argv[1]).open('a').write('x')",
         str(target)],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert target.read_text() == "xx"
    payload = json.loads(result.stdout)
    assert payload["status"] == "local_batch_complete"
    assert payload["work_items_processed"] == 2
    assert payload["work_items_completed"] == 2
    assert payload["remaining_unverified_ids"] == []
    assert payload["batch_complete"] is True
    assert payload["mission_complete"] is False
    restored = ContinuousControlPlane.from_config(JsonlControlStore(queue), config)
    assert all(restored.work[i].state is WorkState.COMPLETE for i in ids)
