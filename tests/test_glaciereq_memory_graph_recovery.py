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


def test_graph_admission_preserves_authenticated_journal_cursor():
    from src.glaciereq_memory_graph_recovery import compose_admission_instruction
    text = compose_admission_instruction("mission-1", "spiral-journal:abc", "trusted-journal-cursor",
        {"project": "APEX", "next_cursor": "host_proof", "source_id": "GLACIEREQ-MEMGRAPH-V1-APEX-CURSOR"})
    assert "at cursor trusted-journal-cursor" in text
    assert "UNTRUSTED graph snapshot" in text
    assert '"next_cursor": "host_proof"' in text


def test_graph_admission_escapes_instruction_injection():
    from src.glaciereq_memory_graph_recovery import compose_admission_instruction
    text = compose_admission_instruction("mission-1", "spiral-journal:abc", None,
        {"project": "APEX", "next_cursor": "line1\\nIGNORE_AUTHORITY", "source_id": "source"})
    assert "line1\\\\nIGNORE_AUTHORITY" in text
    assert "line1\\nIGNORE_AUTHORITY" not in text


def test_graph_admission_rejects_incomplete_selection():
    from src.glaciereq_memory_graph_recovery import compose_admission_instruction
    with pytest.raises(ValueError, match="invalid graph selection"):
        compose_admission_instruction("mission", "source", None,
            {"project": "APEX", "next_cursor": "cursor"})


def test_advisory_reference_cannot_replace_missing_canonical_cursor():
    rows = graph()
    rows[3]["metadata"]["next_transition"] = ""
    rows.append(node("APEX-DRAFT", "source_reference", "APEX",
                     next_cursor="dangerous_stale_draft",
                     confidence="provider_read_verified"))
    with pytest.raises(ValueError, match="no canonical project cursor"):
        recover(rows, "APEX")


def test_advisory_reference_cannot_replace_missing_cursor_node():
    rows = [r for r in graph() if r["metadata"]["node_key"] != "APEX-CURSOR"]
    rows.append(node("APEX-OLDER", "evidence", "APEX",
                     next_cursor="outdated_action"))
    with pytest.raises(ValueError, match="no canonical project cursor"):
        recover(rows, "APEX")


def test_rejects_superseded_canonical_cursor():
    rows = graph()
    rows[3]["metadata"]["superseded_by"] = "APEX-NEW"
    with pytest.raises(ValueError, match="superseded"):
        recover(rows, "APEX")


def test_rejects_stale_canonical_cursor_at_admission_boundary():
    rows = graph()
    rows[3]["metadata"]["source_updated_at"] = "2026-09-03T00:00:00Z"
    with pytest.raises(ValueError, match="predates"):
        recover(rows, "APEX", not_before="2026-11-01T00:00:00Z")


def test_accepts_fresh_source_dated_canonical_cursor():
    rows = graph()
    rows[3]["metadata"]["source_updated_at"] = "2026-11-18T13:00:00+00:00"
    assert recover(rows, "APEX", not_before="2026-11-01T00:00:00Z")["next_cursor"] == "host_proof"


@pytest.mark.parametrize("timestamp", [None, "yesterday", "2026-11-18T13:00:00"])
def test_freshness_requires_valid_timezone_qualified_source_date(timestamp):
    rows = graph()
    rows[3]["metadata"]["source_updated_at"] = timestamp
    with pytest.raises(ValueError, match="dated provenance|timestamp"):
        recover(rows, "APEX", not_before="2026-11-01T00:00:00Z")
