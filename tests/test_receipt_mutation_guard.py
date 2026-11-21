"""Deterministic adversarial tests for receipt mutation during inspection."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import inspect_execution_receipt as inspector


def test_same_length_rewrite_during_inspection_fails_closed(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"status":"pending_unverified"}')
    original = inspector.os.fstat
    calls = 0

    def rewriting_fstat(fd):
        nonlocal calls
        result = original(fd)
        calls += 1
        if calls == 1:
            receipt.write_text('{"status":"launched_unverified"}')
        return result

    monkeypatch.setattr(inspector.os, "fstat", rewriting_fstat)
    result = inspector.inspect(receipt)
    assert result["status"] == "inspection_failed"
    assert result["retry_authorized"] is False


def test_append_during_inspection_fails_closed(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"status": "pending_unverified"}))
    original = inspector.os.fstat
    calls = 0

    def appending_fstat(fd):
        nonlocal calls
        result = original(fd)
        calls += 1
        if calls == 1:
            with receipt.open("ab") as handle:
                handle.write(b" ")
        return result

    monkeypatch.setattr(inspector.os, "fstat", appending_fstat)
    result = inspector.inspect(receipt)
    assert result["status"] == "inspection_failed"
    assert result["retry_authorized"] is False
