from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import auto_boot  # noqa: E402
from startup_continuation import record_startup_continuation  # noqa: E402


def test_continuation_record_is_durable_non_authorizing_and_hash_bound(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", str(tmp_path))
    record = record_startup_continuation(
        "operator fidelity / preflight",
        ("missing receipt",),
        request={"request_type": "operator_fidelity", "external_action_authorized": False},
        environment_key="GLACIEREQ_OPERATOR_FIDELITY_STATUS",
    )

    assert record["status"] == "continuation_required"
    assert record["gate"] == "operator_fidelity___preflight"
    assert record["local_recovery_authorized"] is True
    assert record["external_action_authorized"] is False
    assert record["record_sha256"]
    assert record["persistence"] == "durable_local_record"
    persisted = json.loads((tmp_path / f"{record['gate']}-{record['continuation_id'][:16]}.json").read_text(encoding="utf-8"))
    assert persisted["continuation_id"] == record["continuation_id"]
    assert persisted["errors"] == ["missing receipt"]


def test_automatic_boot_strict_compatibility_mode_returns_continuation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")
    monkeypatch.delenv("CASEY_AUTO_BOOT_DISABLE", raising=False)
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    monkeypatch.setenv("GLACIEREQ_STARTUP_CONTINUATION_DIR", str(tmp_path))

    validation = auto_boot.automatic_boot()

    assert validation is not None
    assert validation.ok is False
    assert validation.status == "continuation_required"
    assert auto_boot.os.environ["CASEY_BOOT_STATUS"] == "continuation_required"
    assert auto_boot.os.environ["GLACIEREQ_EXTERNAL_ACTION_AUTHORIZED"] == "0"
    records = list(tmp_path.glob("auto_boot-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["request"]["receipt_errors"] == ["no boot receipt supplied"]
