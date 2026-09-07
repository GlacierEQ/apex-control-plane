from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from auto_boot import load_manifest, normalize_profiles, required_note_versions
from prime_directive_boot import validate_combined_receipt
from prime_directive_enforcer import GateViolation, StartupGateEnforcer, load_policy


STATE_CONTENT = (ROOT / "STATE.md").read_text(encoding="utf-8")
PROMPT_CONTENT = (ROOT / "AGENT_SYSTEM_PROMPT.md").read_text(encoding="utf-8")


def _tool_call(name: str, arguments: object, call_id: str) -> dict:
    if name == "personal_context.search" and isinstance(arguments, dict):
        arguments = dict(arguments)
        arguments.setdefault(
            "material_rediscovery_justification",
            "state_not_available_in_usable_form",
        )
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


def _valid_combined_validation(*, empty_memory: bool = False, reuse_memory: bool = True):
    manifest = load_manifest()
    policy = load_policy()
    profiles = normalize_profiles(manifest, ["systems"])
    versions = required_note_versions(manifest, profiles)
    memory_state = (
        {
            "mode": "reused",
            "status": "complete",
            "source": "conversation-context:current-worker",
            "item_count": 2,
            "known_state_available": True,
            "material_rediscovery_justification": "",
        }
        if reuse_memory and not empty_memory
        else {
            "mode": "searched",
            "status": "empty" if empty_memory else "complete",
            "source": "personal_context.search:current-task",
            "item_count": 0 if empty_memory else 1,
            "known_state_available": False,
            "material_rediscovery_justification": "state_not_available_in_usable_form",
            "tool": "personal_context.search",
            "query": "current task and user project context",
        }
    )
    loaded_tools = ["GitHub.fetch_file", "api_tool.list_resources"]
    if memory_state["mode"] == "searched":
        loaded_tools.append("personal_context.search")
    receipt = {
        "boot_manifest_id": manifest["canonical_mem_manifest"]["id"],
        "boot_manifest_version": manifest["canonical_mem_manifest"]["version"],
        "mem_collection_id": manifest["mem_collection"]["id"],
        "boot_profile": list(profiles),
        "notes_loaded": [
            {"id": note_id, "version": version}
            for note_id, version in versions.items()
        ],
        "sources_opened": [
            {"system": "github", "object_id": "source-1", "version": "abc123"}
        ],
        "repository_receipts": [
            {
                "repository": "GlacierEQ/apex-control-plane",
                "revision": "abc123",
                "checked_at": "2026-08-04T08:00:00Z",
            }
        ],
        "case_lane": None,
        "matter_lane": None,
        "deadline_check": {
            "status": "not_relevant",
            "source_ids": [],
            "reason": "systems profile",
        },
        "restricted_context": False,
        "current_task": "verify the Prime Directive middleware",
        "next_material_action": "run startup tests",
        "boot_status": "complete",
        "blockers": [],
        "memory_state": memory_state,
        "ground_truth_files_loaded": [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "source": f"GitHub.fetch_file:{row['path']}",
            }
            for row in policy["ground_truth_files"]
        ],
        "tool_inventory": {
            "tool": "api_tool.list_resources",
            "status": "complete",
            "loaded_tools": loaded_tools,
            "gaps": [],
        },
    }
    return validate_combined_receipt(
        manifest,
        policy,
        receipt,
        profiles,
        restricted_authorized=False,
    )


def _record_first_three_stages(enforcer: StartupGateEnforcer) -> None:
    enforcer.record_memory_state_reuse(
        source="conversation-context:current-worker",
        item_count=2,
        known_state_available=True,
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
        {"resources": [{"name": "GitHub.fetch_file"}]},
        call_id="tools-1",
        success=True,
    )


def _complete_gate(enforcer: StartupGateEnforcer) -> None:
    _record_first_three_stages(enforcer)
    assert enforcer.gate_passed is False
    enforcer.attach_boot_validation(_valid_combined_validation())


def test_text_before_gate_is_replaced_with_hard_correction() -> None:
    enforcer = StartupGateEnforcer()
    result = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "I don't have access to that."}
    )

    assert result["type"] == "hard_correction"
    assert result["gate_passed"] is False
    assert "memory_state" in result["missing_stages"]
    assert "current_source_open" in result["missing_stages"]
    assert "receipt_validation" in result["missing_stages"]
    assert "Consult relevant already-available memory/continuity state first" in result["content"]


def test_reused_memory_state_advances_without_search_tool_call() -> None:
    enforcer = StartupGateEnforcer()
    snapshot = enforcer.record_memory_state_reuse(
        source="conversation-context:current-worker",
        item_count=3,
        known_state_available=True,
    )

    assert snapshot.memory_search_complete is True
    assert snapshot.memory_search_empty is False
    assert snapshot.memory_state_mode == "reused"
    assert "personal_context.search" not in snapshot.tools_invoked
    assert "memory_state" not in snapshot.missing_stages
    assert snapshot.gate_passed is False


def test_reused_memory_state_requires_provenance_and_nonempty_state() -> None:
    enforcer = StartupGateEnforcer()
    with pytest.raises(GateViolation, match="provenance source"):
        enforcer.record_memory_state_reuse(
            source="", item_count=2, known_state_available=True
        )
    with pytest.raises(GateViolation, match="item_count>=1"):
        enforcer.record_memory_state_reuse(
            source="conversation-context:current-worker",
            item_count=0,
            known_state_available=True,
        )


def test_reused_memory_state_requires_structured_locator_and_available_state() -> None:
    enforcer = StartupGateEnforcer()
    with pytest.raises(GateViolation, match="structured class:locator"):
        enforcer.record_memory_state_reuse(
            source="invented-projection",
            item_count=2,
            known_state_available=True,
        )
    with pytest.raises(GateViolation, match="known_state_available=true"):
        enforcer.record_memory_state_reuse(
            source="conversation-context:current-worker",
            item_count=2,
            known_state_available=False,
        )


def test_successful_search_without_material_reason_does_not_advance() -> None:
    enforcer = StartupGateEnforcer()
    payload = _tool_call(
        "personal_context.search",
        {
            "query": "case",
            "material_rediscovery_justification": "",
        },
        "memory-1",
    )
    enforcer.intercept_llm_response(payload)

    with pytest.raises(GateViolation, match="material_rediscovery_justification"):
        enforcer.record_tool_result(
            "personal_context.search",
            {"results": [{"id": "one"}]},
            call_id="memory-1",
            success=True,
        )

    snapshot = enforcer.snapshot()
    assert snapshot.memory_search_complete is False
    assert snapshot.memory_state_mode == ""


def test_successful_search_with_unknown_material_reason_does_not_advance() -> None:
    enforcer = StartupGateEnforcer()
    payload = _tool_call(
        "personal_context.search",
        {
            "query": "case",
            "material_rediscovery_justification": "because_search_is_easy",
        },
        "memory-1",
    )
    enforcer.intercept_llm_response(payload)

    with pytest.raises(GateViolation, match="is not allowed"):
        enforcer.record_tool_result(
            "personal_context.search",
            {"results": [{"id": "one"}]},
            call_id="memory-1",
            success=True,
        )

    snapshot = enforcer.snapshot()
    assert snapshot.memory_search_complete is False
    assert snapshot.memory_state_mode == ""


def test_pre_gate_tool_call_suppresses_all_provider_text_fields() -> None:
    enforcer = StartupGateEnforcer()
    payload = _tool_call("personal_context.search", {"query": "case"}, "memory-1")
    payload.update(
        {
            "refusal": "hidden refusal",
            "reasoning": "hidden reasoning",
            "output": "hidden output",
            "output_text": "hidden output text",
        }
    )
    result = enforcer.intercept_llm_response(payload)

    assert result["tool_calls"]
    for field in ("content", "refusal", "reasoning", "output", "output_text"):
        assert result[field] == ""
    assert enforcer.gate_passed is False


def test_nested_provider_text_is_suppressed_without_removing_tool_data() -> None:
    enforcer = StartupGateEnforcer()
    payload = _tool_call("personal_context.search", {"query": "case"}, "memory-1")
    payload["output"] = [
        {"type": "message", "content": "hidden"},
        {"type": "tool_use", "name": "personal_context.search"},
    ]
    result = enforcer.intercept_llm_response(payload)

    assert result["output"][0]["content"] == ""
    assert result["output"][1]["name"] == "personal_context.search"


def test_search_call_without_successful_result_does_not_advance_memory_state() -> None:
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
    assert snapshot.memory_state_mode == ""
    assert snapshot.gate_passed is False


def test_successful_search_advances_memory_state_as_searched() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.intercept_llm_response(
        _tool_call("personal_context.search", {"query": "case"}, "memory-1")
    )
    snapshot = enforcer.record_tool_result(
        "personal_context.search",
        {"results": [{"id": "one"}]},
        call_id="memory-1",
        success=True,
    )

    assert snapshot.memory_search_complete is True
    assert snapshot.memory_search_empty is False
    assert snapshot.memory_state_mode == "searched"
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
    assert snapshot.memory_search_empty is True
    assert snapshot.memory_state_mode == "searched"
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


def test_inventory_requires_nonempty_structured_result() -> None:
    enforcer = StartupGateEnforcer()

    for call_id, result in (
        ("tools-1", "GitHub is loaded"),
        ("tools-2", {"resources": []}),
        ("tools-3", {"tools": {}}),
        ("tools-4", {"results": [{"name": ""}]}),
    ):
        enforcer.intercept_llm_response(
            _tool_call("api_tool.list_resources", {"paths": ["GitHub"]}, call_id)
        )
        snapshot = enforcer.record_tool_result(
            "api_tool.list_resources",
            result,
            call_id=call_id,
            success=True,
        )
        assert snapshot.tool_inventory_complete is False

    enforcer.intercept_llm_response(
        _tool_call("api_tool.list_resources", {"paths": ["GitHub"]}, "tools-5")
    )
    good = enforcer.record_tool_result(
        "api_tool.list_resources",
        {"resources": [{"name": "GitHub.fetch_file"}]},
        call_id="tools-5",
        success=True,
    )
    assert good.tool_inventory_complete is True


def test_partial_startup_does_not_complete_documented_five_stage_gate() -> None:
    enforcer = StartupGateEnforcer()
    _record_first_three_stages(enforcer)
    snapshot = enforcer.snapshot()

    assert snapshot.memory_state_mode == "reused"
    assert snapshot.gate_passed is False
    assert snapshot.current_source_complete is False
    assert snapshot.receipt_validation_complete is False
    assert "current_source_open" in snapshot.missing_stages
    assert "receipt_validation" in snapshot.missing_stages


def test_sealed_reuse_validation_completes_gate_and_allows_text() -> None:
    enforcer = StartupGateEnforcer()
    _complete_gate(enforcer)

    snapshot = enforcer.snapshot()
    assert snapshot.gate_passed is True
    assert snapshot.memory_state_mode == "reused"
    assert snapshot.current_source_complete is True
    assert snapshot.receipt_validation_complete is True
    result = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "Execution completed with receipts."}
    )
    assert result["content"] == "Execution completed with receipts."


def test_empty_memory_phrase_is_prepended_once_only_after_searched_empty_state() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.attach_boot_validation(
        _valid_combined_validation(empty_memory=True, reuse_memory=False)
    )

    first = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "Execution continues."}
    )
    second = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "Second response."}
    )

    assert first["content"] == (
        "searched memory, no matching entry\n\nExecution continues."
    )
    assert second["content"] == "Second response."


def test_reused_memory_never_emits_empty_search_phrase() -> None:
    enforcer = StartupGateEnforcer()
    enforcer.attach_boot_validation(_valid_combined_validation())
    result = enforcer.intercept_llm_response(
        {"role": "assistant", "content": "Continue from known state."}
    )
    assert result["content"] == "Continue from known state."


def test_attach_boot_validation_rejects_forged_mapping() -> None:
    enforcer = StartupGateEnforcer()

    with pytest.raises(GateViolation, match="not authentic"):
        enforcer.attach_boot_validation(
            {"ok": True, "status": "complete", "errors": []}
        )


def test_mark_gate_passed_requires_all_five_stages() -> None:
    enforcer = StartupGateEnforcer()
    _record_first_three_stages(enforcer)

    with pytest.raises(GateViolation, match="current_source_open"):
        enforcer.mark_gate_passed()

    enforcer.attach_boot_validation(_valid_combined_validation())
    snapshot = enforcer.mark_gate_passed()
    assert snapshot.gate_passed is True
    assert snapshot.missing_stages == ()


def test_pending_calls_are_bounded() -> None:
    enforcer = StartupGateEnforcer()
    for index in range(300):
        enforcer.intercept_llm_response(
            _tool_call("personal_context.search", {"query": str(index)}, f"call-{index}")
        )

    assert len(enforcer._state.pending_calls) == 256
    assert "call-0" not in enforcer._state.pending_calls
    assert "call-299" in enforcer._state.pending_calls


def test_terminal_block_rejects_later_calls_and_results() -> None:
    enforcer = StartupGateEnforcer()
    terminal = None
    for _ in range(9):
        terminal = enforcer.intercept_llm_response(
            {"role": "assistant", "content": "premature text"}
        )

    assert terminal is not None
    assert terminal["type"] == "startup_gate_terminal_block"
    later = enforcer.intercept_llm_response(
        _tool_call("personal_context.search", {"query": "case"}, "late-call")
    )
    assert later["type"] == "startup_gate_terminal_block"
    with pytest.raises(GateViolation, match="terminally blocked"):
        enforcer.record_tool_result(
            "personal_context.search",
            {"results": []},
            call_id="late-call",
            success=True,
        )


def test_audit_log_never_contains_prompt_or_tool_arguments() -> None:
    enforcer = StartupGateEnforcer(load_policy())
    enforcer.intercept_llm_response(
        _tool_call(
            "personal_context.search",
            {"query": "private task details"},
            "memory-1",
        )
    )
    enforcer.record_memory_state_reuse(
        source="conversation-context:private-state",
        item_count=1,
        known_state_available=True,
    )
    serialized = repr(enforcer.audit_events())

    assert "private task details" not in serialized
    assert "private-state" not in serialized
    assert "arguments" not in serialized
    assert "content" not in serialized
