"""Entrypoint must execute a real route or report idle, never fabricate progress."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "control_plane.py"


def run_entry(*args: str):
    result = subprocess.run([sys.executable, str(ENTRY), *args], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_no_event_does_not_claim_route_executed():
    result = run_entry()
    assert result["status"] == "idle"
    assert result["routes_run"] == 0


def test_event_is_ingested_and_independently_read_back(tmp_path):
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({
        "event_type": "gmail.reply.received",
        "source_system": "gmail",
        "subject_id": "TEST-CASE",
        "correlation_id": "corr-test",
        "payload": {"message_id": "m1"},
        "provenance_refs": ["gmail://message/m1"],
    }))
    state = tmp_path / "apex-state"
    result = run_entry("--event-file", str(event_file), "--state-dir", str(state))
    assert result["status"] == "ingested"
    assert result["created_work"] == 1
    assert result["receipt"]["diff"]["events"] == 1
    assert result["receipt"]["diff"]["work"] == 1
    assert result["readback"]["events"] == 1
    assert result["readback"]["work"] == 1
    assert (state / "events.jsonl").exists()
    assert (state / "work.jsonl").exists()

    again = run_entry("--event-file", str(event_file), "--state-dir", str(state))
    assert again["status"] == "duplicate"
    assert again["created_work"] == 0
    assert again["receipt"]["diff"]["events"] == 0
    assert again["readback"]["work"] == 1
