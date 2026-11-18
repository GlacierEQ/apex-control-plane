"""Fail-closed, source-qualified GLACIEREQ memory graph cursor selection.

This is a deterministic consumer of already retrieved rows from apex_memories.
It does not fetch credentials, create a mission, or claim ChatGPT host injection.
"""
from __future__ import annotations

GRAPH = "GLACIEREQ-MEMGRAPH-V1"


def recover(rows, project):
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    nodes = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid row")
        meta = row.get("metadata") or {}
        if not isinstance(meta, dict):
            raise ValueError("invalid metadata")
        if row.get("memory_type") != "structured_memory_graph_node" or meta.get("graph_id") != GRAPH:
            continue
        key = meta.get("node_key")
        if not isinstance(key, str) or not key:
            raise ValueError("missing node key")
        if key in nodes:
            raise ValueError("duplicate graph key: " + key)
        nodes[key] = row
    if not nodes:
        raise ValueError("no graph")
    for key, row in nodes.items():
        parent = row["metadata"].get("parent_key")
        if parent and parent not in nodes:
            raise ValueError("orphan: " + key)
        seen = {key}
        while parent:
            if parent in seen:
                raise ValueError("cycle: " + key)
            seen.add(parent)
            parent = nodes[parent]["metadata"].get("parent_key")
    if project not in nodes:
        raise ValueError("unknown project")

    def descendant(key):
        while key:
            if key == project:
                return True
            key = nodes[key]["metadata"].get("parent_key")
        return False

    candidates = []
    for key, row in nodes.items():
        meta = row["metadata"]
        if not descendant(key) or not row.get("source_id"):
            continue
        explicit = meta.get("node_kind") == "cursor"
        action = meta.get("next_transition") if explicit else meta.get("next_cursor")
        if not action:
            continue
        if not isinstance(action, str) or not action.strip():
            raise ValueError("invalid cursor: " + key)
        candidates.append((key, row, explicit, action))
    if not candidates:
        raise ValueError("no source-qualified cursor")
    explicit = [item for item in candidates if item[2]]
    if len(explicit) > 1:
        raise ValueError("ambiguous canonical cursor")
    if not explicit:
        # Source-reference next_cursor values are advisory and may be stale.
        # Never promote an arbitrary draft/reference into an execution directive
        # when the owning project's canonical cursor is absent.
        raise ValueError("no canonical project cursor; refuse advisory fallback")
    key, row, _, action = explicit[0]
    return {
        "project": project,
        "node_key": key,
        "source_id": row["source_id"],
        "next_cursor": action,
        "cursor_description": row.get("content") if explicit else None,
        "authority": row.get("authority_status", "unresolved"),
        "automatic_host_invocation_verified": False,
    }


def compose_admission_instruction(mission_id, source_ref, journal_cursor, graph_selection=None):
    """Preserve authenticated journal precedence; annotate separate graph provenance."""
    instruction = (f"Continue mission {mission_id} from {source_ref} "
                   f"at cursor {journal_cursor or 'initial'}")
    if graph_selection is not None:
        for field in ("project", "next_cursor", "source_id"):
            if not isinstance(graph_selection.get(field), str) or not graph_selection[field].strip():
                raise ValueError("invalid graph selection field: " + field)
        # JSON-escaped representation prevents control characters from forging a
        # second task instruction. A graph export is not an authenticated fact.
        import json
        provenance = {field: graph_selection[field] for field in ("project", "next_cursor", "source_id")}
        instruction += ("; separate UNTRUSTED graph snapshot suggests " +
                        json.dumps(provenance, sort_keys=True) +
                        "; verify owning source before action")
    return instruction
