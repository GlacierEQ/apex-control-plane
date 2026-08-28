from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "admit_session_connector_receipts.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("apex_receipt_admission", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_admission_writes_safe_receipt_ledger_without_provider_material(tmp_path):
    module = load_script_module()
    observed_at = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    raw_provider_material = tmp_path / "drive.json"
    raw_provider_material.write_text(
        '{"files":[{"id":"drive-1","name":"private APEX source"}]}',
        encoding="utf-8",
    )
    manifest = tmp_path / "observations.json"
    manifest.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "connector": "google_workspace",
                        "operation": "drive.search",
                        "profile": "current_source_review",
                        "target": {
                            "query_label": "APEX metadata check",
                            "provider_input": {
                                "q": "name contains 'APEX'",
                                "pageSize": 1,
                            },
                        },
                        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                        "source_refs": ["gws://drive/files/list/test"],
                        "observation_path": str(raw_provider_material),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ledger = tmp_path / "receipts.jsonl"

    result = module.admit_manifest(
        manifest_path=manifest,
        receipt_ledger_path=ledger,
        commit_sha="a" * 40,
        now=observed_at,
    )

    content = ledger.read_text(encoding="utf-8")
    assert result["status"] == "accepted"
    assert result["receipt_count"] == 1
    assert result["external_action_authorized"] is False
    assert "private APEX source" not in content
    assert "content_sha256" in content
    assert "external_action_authorized" in content
