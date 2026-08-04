from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from prime_directive_enforcer import GateViolation, StartupGateEnforcer, load_policy


STATE_CONTENT = (ROOT / "STATE.md").read_text(encoding="utf-8")
PROMPT_CONTENT = (ROOT / "AGENT_SYSTEM_PROMPT.md").read_text(encoding="utf-8")


def _tool_call(name: str, arguments: object, call_id: str) -> dict:
    return {
        "role": "assistant",
        "content": "I will explain this first.",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


def _complete_gate(enforcer: StartupGateEnforcer) -> None:
    enforcer.intercept_llm_response(
        _tool_call(
            "personal_context.search",
            {"query": "current task and user project context"},
            "memory-1",
        )
    )
    enforcer.record_tool_result(
        "personal_context.search",
        {"results": []},
        call_id="memory-1",
        success=True,
    )

    for call_id, path, content in (
        ("state-1", "STATE.md", STATE_CONTENT),
        ("prompt-1", "AGENT_SYSTEM_PROMPT.md", PROMPT_CONTENT),
    ):
        enforcer.intercept_llm_response(
            _tool_call("GitHub.fetch_file", {"path": path}, call_id)
        )
        enforcer.record_tool_result(
            "GitHub.fetch_file",
            {"path": path, "content": content},
            call_id=call_id,
            success=True,
        )

    enforcer.intercept_llm_response(
        _tool_call("api_tool.list_resources", {"paths": ["GitHub"]}, "tools-1")
    )
    enforcer.record_tool_result(
        "api_tool.list_resources",
        {"tools": [{"name": "GitHub.fetch_file"}]},
        call_id="tools-1",
        success=True,
    )


def test_text_before_gate_is_replaced_with_hard_correction() -> None:
    enforcer = StartupGateEnforcer()
    result = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "I don't have access to that."}
    )

    assert result["type"] == "hard_correction"
    assert result["gate_passed"] is False
    assert "memory_search" in result["missing_stages"]
    assert "Do not apologize" in result["content"]


def test_pre_gate_tool_call_passes_but_conversational_content_is_removed() -> None:
    enforcer = StartupGateEnforcer()
    result = enforcer.intercept_llm_response(
        _tool_call("personal_context.search", {"query": "case"}, "memory-1")
    )

    assert result["tool_calls"]
    assert result["content"] == ""
    assert enforcer.gate_passed is False


def test_tool_call_without_successful_result_does_not_advance_gate() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.intercept_llm_response(
        _tool_call("personal_context.search", {"query": "case"}, "memory-1")
    )
    snapshot = enforcer.record_tool_result(
        "personal_context.search",
        {"error": "timeout"},
        call_id="memory-1",
        success=False,
    )

    assert snapshot.memory_search_complete is False
    assert snapshot.gate_passed is False


def test_empty_memory_search_result_still_counts_as_searched() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.intercept_llm_response(
        _tool_call("personal_context.search", {"query": "unmatched"}, "memory-1")
    )
    snapshot = enforcer.record_tool_result(
        "personal_context.search",
        {"results": []},
        call_id="memory-1",
        success=True,
    )

    assert snapshot.memory_search_complete is True
    assert snapshot.gate_passed is False


def test_ground_truth_requires_exact_pinned_hash() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.intercept_llm_response(
        _tool_call("GitHub.fetch_file", {"path": "STATE.md"}, "state-1")
    )
    mismatch = enforcer.record_tool_result(
        "GitHub.fetch_file",
        {"path": "STATE.md", "content": STATE_CONTENT + "\nmodified"},
        call_id="state-1",
        success=True,
    )
    assert "STATE.md" not in mismatch.ground_truth_files_loaded

    enforcer.intercept_llm_response(
        _tool_call("GitHub.fetch_file", {"path": "STATE.md"}, "state-2")
    )
    verified = enforcer.record_tool_result(
        "GitHub.fetch_file",
        {"path": "STATE.md", "content": STATE_CONTENT},
        call_id="state-2",
        success=True,
    )
    assert "STATE.md" in verified.ground_truth_files_loaded


def test_inventory_requires_structured_result() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.intercept_llm_response(
        _tool_call("api_tool.list_resources", {"paths": ["GitHub"]}, "tools-1")
    )
    bad = enforcer.record_tool_result(
        "api_tool.list_resources",
        "GitHub is loaded",
        call_id="tools-1",
        success=True,
    )
    assert bad.tool_inventory_complete is False

    enforcer.intercept_llm_response(
        _tool_call("api_tool.list_resources", {"paths": ["GitHub"]}, "tools-2")
    )
    good = enforcer.record_tool_result(
        "api_tool.list_resources",
        {"resources": [{"name": "GitHub.fetch_file"}]},
        call_id="tools-2",
        success=True,
    )
    assert good.tool_inventory_complete is True


def test_complete_gate_allows_normal_text() -> None:
    enforcer = StartupGateEnforcer()
    _complete_gate(enforcer)

    assert enforcer.gate_passed is True
    result = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "Execution completed with receipts."}
    )
    assert result["content"] == "Execution completed with receipts."


def test_mark_gate_passed_rejects_unverified_proof() -> None:
    enforcer = StartupGateEnforcer()

    with pytest.raises(GateViolation, match="not a complete"):
        enforcer.mark_gate_passed(
            {"ok": False, "status": "blocked", "errors": ["missing source"]}
        )


def test_mark_gate_passed_accepts_complete_verified_boot_proof() -> None:
    enforcer = StartupGateEnforcer()
    snapshot = enforcer.mark_gate_passed(
        {"ok": True, "status": "complete", "errors": []}
    )

    assert snapshot.gate_passed is True
    assert snapshot.missing_stages == ()


def test_audit_log_never_contains_prompt_or_tool_arguments() -> None:
    enforcer = StartupGateEnforcer(load_policy())
    enforcer.intercept_llm_response(
        _tool_call(
            "personal_context.search",
            {"query": "private task details"},
            "memory-1",
        )
    )
    serialized = repr(enforcer.audit_events())

    assert "private task details" not in serialized
    assert "arguments" not in serialized
    assert "content" not in serialized
