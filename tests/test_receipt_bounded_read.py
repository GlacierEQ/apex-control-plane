"""Adversarial receipt size tests for the executable inspector."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from inspect_execution_receipt import inspect


def test_oversize_receipt_fails_closed(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(b'{"status":"pending_unverified","padding":"' + b'x' * (1024 * 1024) + b'"}')
    result = inspect(receipt)
    assert result["status"] == "inspection_failed"
    assert result["retry_authorized"] is False


def test_small_pending_receipt_remains_unverified(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"status": "pending_unverified"}))
    result = inspect(receipt)
    assert result["status"] == "inspected_unverified"
    assert result["outcome_verified"] is False
    assert result["retry_authorized"] is False
