"""Full capability-field selection must not silently truncate available resources."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from apex_proactive import top_k_tools


def test_default_keeps_full_ranked_capability_field():
    tools = [
        {"name": f"browser-{i}", "description": "browser store price availability"}
        for i in range(7)
    ] + [{"name": "other", "description": "network"}]
    selected = top_k_tools(tools, "browser store price availability")
    assert [t["name"] for t in selected] == [t["name"] for t in tools]


def test_explicit_k_is_still_respected_for_callers_that_request_it():
    tools = [{"name": f"browser-{i}", "description": "browser"} for i in range(7)]
    assert len(top_k_tools(tools, "browser", k=3)) == 3


def test_default_empty_query_does_not_drop_capabilities():
    tools = [{"name": f"tool-{i}", "description": "various capabilities"} for i in range(17)]
    assert top_k_tools(tools, "") == tools
