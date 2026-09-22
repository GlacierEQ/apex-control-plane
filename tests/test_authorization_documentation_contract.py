from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPROVED_OPERATION_DOC = ROOT / "docs" / "APEX_APPROVED_OPERATION_BRIDGE.md"
CONNECTOR_BRIDGE_DOC = ROOT / "docs" / "APEX_CONNECTOR_BRIDGE.md"


def test_approved_operation_doc_preserves_source_bound_authorization() -> None:
    text = APPROVED_OPERATION_DOC.read_text(encoding="utf-8")

    assert "plan/batch" in text
    assert "action-class" in text
    assert "routine constituent action" in text
    assert "newly manufactured per-action approval" in text
    assert "Every mutation still needs its own exact approval record" not in text
    assert "explicitly approved that exact mutation" not in text


def test_connector_docs_agree_on_authority_inheritance() -> None:
    approved = APPROVED_OPERATION_DOC.read_text(encoding="utf-8")
    bridge = CONNECTOR_BRIDGE_DOC.read_text(encoding="utf-8")

    for text in (approved, bridge):
        assert "source-bound" in text
        assert "routine constituent" in text
        assert "plan/batch" in text

    assert "Destructive actions or material strategy deltas require renewed" in approved
    assert "Destructive actions or material strategy deltas require renewed" in bridge
