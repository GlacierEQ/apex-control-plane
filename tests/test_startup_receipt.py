from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from auto_boot import BootError
from startup_receipt import receipt_from_environment


def test_receipt_from_environment_returns_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_PATH", raising=False)
    assert receipt_from_environment() is None


def test_receipt_from_environment_reads_inline_json(monkeypatch) -> None:
    monkeypatch.setenv("CASEY_BOOT_RECEIPT_JSON", '{"status":"complete"}')
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_PATH", raising=False)
    assert receipt_from_environment() == {"status": "complete"}


def test_receipt_from_environment_reads_json_file(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    monkeypatch.delenv("CASEY_BOOT_RECEIPT_JSON", raising=False)
    monkeypatch.setenv("CASEY_BOOT_RECEIPT_PATH", str(path))
    assert receipt_from_environment() == {"status": "complete"}


def test_receipt_from_environment_rejects_ambiguous_sources(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CASEY_BOOT_RECEIPT_JSON", "{}")
    monkeypatch.setenv("CASEY_BOOT_RECEIPT_PATH", str(path))
    with pytest.raises(BootError, match="set only one"):
        receipt_from_environment()
