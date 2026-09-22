from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPROVED_OPERATION_DOC = ROOT / "docs" / "APEX_APPROVED_OPERATION_BRIDGE.md"
CONNECTOR_BRIDGE_DOC = ROOT / "docs" / "APEX_CONNECTOR_BRIDGE.md"

INHERITANCE_SENTENCE = (
    "Routine constituent actions inherit authority only from an independently resolved "
    "Operator source record whose verified scope covers the connector, operation/action class, "
    "target constraints, provider-input constraints, and consequence constraints; no action "
    "request can manufacture that source record."
)
BINDING_SENTENCE = (
    "Concrete provider input, consequence, evidence references, and idempotency are bound into "
    "the action digest after scope validation; that digest is an idempotency/readback binding, "
    "not a new approval."
)
STRATEGY_SENTENCE = (
    "A strategy-changing action outside the verified scope requires a new Operator source record; "
    "a caller-supplied material-strategy flag cannot expand or prove authority."
)
FORBIDDEN = (
    "Every mutation still needs its own exact approval record",
    "explicitly approved that exact mutation",
    "fresh exact per-action approval",
)


def _docs() -> tuple[str, str]:
    return (
        APPROVED_OPERATION_DOC.read_text(encoding="utf-8"),
        CONNECTOR_BRIDGE_DOC.read_text(encoding="utf-8"),
    )


def test_connector_docs_share_the_same_operational_authorization_contract() -> None:
    for text in _docs():
        assert INHERITANCE_SENTENCE in text
        assert BINDING_SENTENCE in text
        assert STRATEGY_SENTENCE in text
        for stale in FORBIDDEN:
            assert stale not in text


def test_approved_operation_doc_requires_independent_source_readback() -> None:
    approved, _ = _docs()
    assert "independently resolves the `source_binding`" in approved
    assert "source/span hashes and active supersession state" in approved
    assert "The request cannot self-attest its own authority." in approved
    assert "`authorization_required` setting remains `true`" in approved
