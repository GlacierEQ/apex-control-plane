"""Regression tests for source-qualified GLACIEREQ graph recovery."""
import pytest
from src.glaciereq_memory_graph_recovery import recover


def node(key, kind, parent, **extra):
    return {
        "source_id": "GLACIEREQ-MEMGRAPH-V1-" + key,
        "memory_type": "structured_memory_graph_node",
        "authority_status": "draft_strategy" if kind == "cursor" else "unresolved",
        "content": key,
        "metadata": {
            "graph_id": "GLACIEREQ-MEMGRAPH-V1",
            "node_key": key,
            "node_kind": kind,
            "parent_key": parent,
            **extra,
        },
    }


def graph():
    return [
        node("ROOT", "mission", None),
        node("APEX", "project", "ROOT"),
        node("OMNI", "project", "ROOT"),
        node("APEX-CURSOR", "cursor", "APEX", next_transition="host_proof"),
        node("OMNI-CURSOR", "cursor", "OMNI", next_transition="mcp_proof"),
    ]


def test_apex_canonical_cursor():
    result = recover(graph(), "APEX")
    assert result["next_cursor"] == "host_proof"
    assert result["authority"] == "draft_strategy"
    assert result["automatic_host_invocation_verified"] is False


def test_project_isolation():
    assert recover(graph(), "OMNI")["next_cursor"] == "mcp_proof"


def test_canonical_overrides_lower_authority_reference():
    rows = graph() + [node("APEX-DRAFT", "source_reference", "APEX", next_cursor="draft_action", confidence="provider_read_verified")]
    assert recover(rows, "APEX")["node_key"] == "APEX-CURSOR"


@pytest.mark.parametrize("mutate,match", [
    (lambda rows: rows.append(rows[3].copy()), "duplicate"),
    (lambda rows: rows[3]["metadata"].update(parent_key="MISSING"), "orphan"),
    (lambda rows: rows[1]["metadata"].update(parent_key="APEX-CURSOR"), "cycle"),
    (lambda rows: rows[3]["metadata"].update(next_transition=""), "no source-qualified"),
    (lambda rows: rows[3].update(source_id=None), "no source-qualified"),
    (lambda rows: rows.append(node("APEX-CURSOR-2", "cursor", "APEX", next_transition="other")), "ambiguous"),
])
def test_fail_closed(mutate, match):
    rows = graph()
    mutate(rows)
    with pytest.raises(ValueError, match=match):
        recover(rows, "APEX")


def test_rejects_missing_project():
    with pytest.raises(ValueError, match="unknown project"):
        recover(graph(), "MISSING")
