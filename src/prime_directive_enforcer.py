"""GlacierEQ Prime Directive response middleware.

This module blocks user-facing model text until the startup gate is proven.
Tool calls are allowed through, but a stage advances only after a successful
tool result is recorded. The module is provider-shape tolerant and stores no
tool arguments or model content in its audit log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import threading
from typing import Any, Mapping, Sequence

LOGGER = logging.getLogger("glaciereq.gatekeeper")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "prime_directive_policy.json"


class GateViolation(RuntimeError):
    """Raised when code attempts to bypass or falsely complete the gate."""


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    name: str
    arguments: Any = None
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    gate_passed: bool
    memory_search_complete: bool
    ground_truth_files_loaded: tuple[str, ...]
    tool_inventory_complete: bool
    tools_invoked: tuple[str, ...]
    successful_tools: tuple[str, ...]
    missing_stages: tuple[str, ...]
    corrections_issued: int
    terminal_blocked: bool


@dataclass(slots=True)
class _MutableState:
    gate_passed: bool = False
    memory_search_complete: bool = False
    ground_truth_files_loaded: set[str] = field(default_factory=set)
    tool_inventory_complete: bool = False
    tools_invoked: list[str] = field(default_factory=list)
    successful_tools: list[str] = field(default_factory=list)
    pending_calls: dict[str, ToolInvocation] = field(default_factory=dict)
    corrections_issued: int = 0
    terminal_blocked: bool = False
    audit_events: list[dict[str, Any]] = field(default_factory=list)


def load_policy(path: Path | None = None) -> dict[str, Any]:
    policy_path = path or DEFAULT_POLICY_PATH
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateViolation(f"Prime Directive policy not found: {policy_path}") from exc
    except json.JSONDecodeError as exc:
        raise GateViolation(f"Invalid Prime Directive policy JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise GateViolation("Prime Directive policy must be a JSON object")
    for key in ("schema_version", "required_stages", "tool_aliases", "ground_truth_files"):
        if key not in payload:
            raise GateViolation(f"Prime Directive policy missing {key}")
    return payload


class StartupGateEnforcer:
    """Intercept model output and enforce the GlacierEQ startup sequence."""

    def __init__(self, policy: Mapping[str, Any] | None = None) -> None:
        self.policy = dict(policy or load_policy())
        self._state = _MutableState()
        self._lock = threading.RLock()
        self._aliases = {
            stage: {_normalize_tool_name(value) for value in values}
            for stage, values in dict(self.policy.get("tool_aliases", {})).items()
        }
        self._required_files = {
            str(row["path"]): str(row["sha256"]).lower()
            for row in self.policy.get("ground_truth_files", ())
            if isinstance(row, Mapping) and row.get("path") and row.get("sha256")
        }
        if not self._required_files:
            raise GateViolation("Prime Directive policy has no ground-truth files")

    @property
    def gate_passed(self) -> bool:
        with self._lock:
            return self._state.gate_passed

    @property
    def tools_invoked(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._state.tools_invoked)

    def intercept_llm_response(self, llm_output: Mapping[str, Any]) -> dict[str, Any]:
        """Return a tool-only message, allowed text, or a hard correction.

        Pre-gate messages containing tool calls are allowed, but any accompanying
        conversational content is removed. Pre-gate text without tool calls is
        rejected regardless of whether it contains a configured failure phrase.
        """
        if not isinstance(llm_output, Mapping):
            raise TypeError("llm_output must be a mapping")

        output = dict(llm_output)
        calls = _extract_tool_calls(output)

        with self._lock:
            if calls:
                for invocation in calls:
                    self._record_invocation(invocation)
                if not self._state.gate_passed and output.get("content"):
                    output["content"] = ""
                return output

            if self._state.gate_passed:
                return output

            return self._hard_correction(str(output.get("content", "")))

    def record_tool_result(
        self,
        tool_name: str,
        result: Any,
        *,
        arguments: Any = None,
        call_id: str | None = None,
        success: bool = True,
    ) -> GateSnapshot:
        """Record one executed tool result and advance only proven stages."""
        normalized = _normalize_tool_name(tool_name)
        with self._lock:
            if call_id and call_id in self._state.pending_calls:
                pending = self._state.pending_calls.pop(call_id)
                if arguments is None:
                    arguments = pending.arguments
                if not normalized:
                    normalized = _normalize_tool_name(pending.name)

            if not normalized:
                raise GateViolation("tool result is missing a tool name")

            if normalized not in self._state.tools_invoked:
                self._state.tools_invoked.append(normalized)

            self._audit("tool_result", tool=normalized, success=bool(success))
            if not success:
                return self.snapshot()

            if normalized not in self._state.successful_tools:
                self._state.successful_tools.append(normalized)

            if self._matches_stage("memory_search", normalized):
                self._state.memory_search_complete = True

            if self._matches_stage("tool_inventory", normalized):
                if _has_structured_inventory(result):
                    self._state.tool_inventory_complete = True

            if self._matches_stage("ground_truth_read", normalized):
                self._record_ground_truth(arguments=arguments, result=result)

            self._complete_if_ready()
            return self.snapshot()

    def mark_gate_passed(self, proof: Any = None) -> GateSnapshot:
        """Complete the gate only from local stage proof or verified boot proof."""
        with self._lock:
            if proof is None:
                if self._missing_stages():
                    raise GateViolation(
                        "cannot mark gate passed; missing: " + ", ".join(self._missing_stages())
                    )
                self._state.gate_passed = True
                self._audit("gate_complete", source="recorded_tool_results")
                return self.snapshot()

            ok = bool(_proof_value(proof, "ok", False))
            status = str(_proof_value(proof, "status", "")).lower()
            errors = _proof_value(proof, "errors", ())
            if not ok or status != "complete" or bool(errors):
                raise GateViolation("boot proof is not a complete successful validation")

            self._state.memory_search_complete = True
            self._state.ground_truth_files_loaded.update(self._required_files)
            self._state.tool_inventory_complete = True
            self._state.gate_passed = True
            self._audit("gate_complete", source="verified_boot_validation")
            return self.snapshot()

    def snapshot(self) -> GateSnapshot:
        with self._lock:
            return GateSnapshot(
                gate_passed=self._state.gate_passed,
                memory_search_complete=self._state.memory_search_complete,
                ground_truth_files_loaded=tuple(
                    sorted(self._state.ground_truth_files_loaded)
                ),
                tool_inventory_complete=self._state.tool_inventory_complete,
                tools_invoked=tuple(self._state.tools_invoked),
                successful_tools=tuple(self._state.successful_tools),
                missing_stages=tuple(self._missing_stages()),
                corrections_issued=self._state.corrections_issued,
                terminal_blocked=self._state.terminal_blocked,
            )

    def audit_events(self) -> tuple[dict[str, Any], ...]:
        """Return metadata-only gate events; no prompts or tool arguments."""
        with self._lock:
            return tuple(dict(event) for event in self._state.audit_events)

    def _record_invocation(self, invocation: ToolInvocation) -> None:
        normalized = _normalize_tool_name(invocation.name)
        if normalized and normalized not in self._state.tools_invoked:
            self._state.tools_invoked.append(normalized)
        if invocation.call_id:
            self._state.pending_calls[invocation.call_id] = ToolInvocation(
                name=normalized,
                arguments=invocation.arguments,
                call_id=invocation.call_id,
            )
        self._audit("tool_call", tool=normalized, success=None)

    def _record_ground_truth(self, *, arguments: Any, result: Any) -> None:
        target_text = _stable_text(arguments).lower()
        result_path = _result_path(result).lower()
        content = _result_content(result)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""

        for path, expected_hash in self._required_files.items():
            path_lower = path.lower()
            target_matches = path_lower in target_text or result_path.endswith(path_lower)
            if target_matches and content_hash == expected_hash:
                self._state.ground_truth_files_loaded.add(path)
                self._audit("ground_truth_verified", file=path, success=True)
            elif target_matches:
                self._audit("ground_truth_hash_mismatch", file=path, success=False)

    def _matches_stage(self, stage: str, tool_name: str) -> bool:
        aliases = self._aliases.get(stage, set())
        if tool_name in aliases:
            return True
        return any(tool_name.endswith(f".{alias}") for alias in aliases if "." not in alias)

    def _complete_if_ready(self) -> None:
        if not self._missing_stages():
            self._state.gate_passed = True
            self._audit("gate_complete", source="recorded_tool_results")

    def _missing_stages(self) -> list[str]:
        missing: list[str] = []
        if not self._state.memory_search_complete:
            missing.append("memory_search")
        missing_files = sorted(set(self._required_files) - self._state.ground_truth_files_loaded)
        if missing_files:
            missing.append("ground_truth_read:" + ",".join(missing_files))
        if not self._state.tool_inventory_complete:
            missing.append("tool_inventory")
        return missing

    def _hard_correction(self, content: str) -> dict[str, Any]:
        self._state.corrections_issued += 1
        trigger = next(
            (
                phrase
                for phrase in self.policy.get("failure_triggers", ())
                if str(phrase).lower() in content.lower()
            ),
            None,
        )
        limit = int(self.policy.get("max_corrections_before_terminal_block", 8))
        if self._state.corrections_issued > limit:
            self._state.terminal_blocked = True
            self._audit("terminal_block", trigger=trigger, success=False)
            return {
                "role": str(self.policy.get("hard_correction_role", "system")),
                "type": "startup_gate_terminal_block",
                "content": (
                    "SYSTEM OVERRIDE: STARTUP GATE REMAINS BLOCKED. "
                    "Do not emit user-facing text. Stop the execution loop and surface "
                    "the unresolved startup-stage receipt to the runtime operator."
                ),
                "missing_stages": self._missing_stages(),
                "gate_passed": False,
            }

        self._audit("hard_correction", trigger=trigger, success=False)
        numbered = []
        for index, stage in enumerate(self._missing_stages(), start=1):
            if stage == "memory_search":
                instruction = "Run memory_search on the task topic and user/project context."
            elif stage.startswith("ground_truth_read:"):
                files = stage.split(":", 1)[1]
                instruction = f"Read and hash-verify the missing ground-truth file(s): {files}."
            else:
                instruction = "List the tools and connectors actually loaded in this worker."
            numbered.append(f"{index}. {instruction}")

        return {
            "role": str(self.policy.get("hard_correction_role", "system")),
            "type": "hard_correction",
            "content": (
                "SYSTEM OVERRIDE: FATAL PRIME DIRECTIVE VIOLATION. "
                "You attempted to emit text before the STARTUP GATE completed. "
                "Do not apologize. Do not output conversational text. "
                "Output the required tool calls now.\n" + "\n".join(numbered)
            ),
            "missing_stages": self._missing_stages(),
            "gate_passed": False,
            "correction_number": self._state.corrections_issued,
        }

    def _audit(self, event_type: str, **fields: Any) -> None:
        event = {
            "event_type": event_type,
            "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        for key, value in fields.items():
            if key in {"arguments", "content", "prompt", "result"}:
                continue
            event[key] = value
        self._state.audit_events.append(event)
        if event_type in {"hard_correction", "terminal_block", "ground_truth_hash_mismatch"}:
            LOGGER.warning("[GATEKEEPER] %s", event_type)


def _normalize_tool_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("::", ".")


def _extract_tool_calls(output: Mapping[str, Any]) -> tuple[ToolInvocation, ...]:
    raw_calls = output.get("tool_calls") or output.get("tools") or ()
    if isinstance(raw_calls, Mapping):
        raw_calls = [raw_calls]
    if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes)):
        return ()

    calls: list[ToolInvocation] = []
    for raw in raw_calls:
        if not isinstance(raw, Mapping):
            continue
        function = raw.get("function")
        tool_use = raw.get("toolUse") or raw.get("tool_use")
        if isinstance(function, Mapping):
            name = function.get("name")
            arguments = function.get("arguments")
        elif isinstance(tool_use, Mapping):
            name = tool_use.get("name")
            arguments = tool_use.get("input")
        else:
            name = raw.get("name")
            arguments = raw.get("arguments", raw.get("input"))
        if name:
            calls.append(
                ToolInvocation(
                    name=str(name),
                    arguments=arguments,
                    call_id=str(raw.get("id") or raw.get("tool_call_id") or "") or None,
                )
            )
    return tuple(calls)


def _stable_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _result_content(result: Any) -> str:
    if isinstance(result, Mapping):
        value = result.get("content")
        if isinstance(value, str):
            return value
        nested = result.get("result")
        if isinstance(nested, Mapping) and isinstance(nested.get("content"), str):
            return str(nested["content"])
    return result if isinstance(result, str) else ""


def _result_path(result: Any) -> str:
    if not isinstance(result, Mapping):
        return ""
    for key in ("path", "file_path", "display_title"):
        value = result.get(key)
        if value:
            return str(value)
    nested = result.get("result")
    return _result_path(nested) if isinstance(nested, Mapping) else ""


def _has_structured_inventory(result: Any) -> bool:
    if isinstance(result, list):
        return True
    if not isinstance(result, Mapping):
        return False
    for key in ("tools", "resources", "results", "connectors"):
        value = result.get(key)
        if isinstance(value, (list, tuple, dict)):
            return True
    nested = result.get("result")
    return _has_structured_inventory(nested) if nested is not None else False


def _proof_value(proof: Any, key: str, default: Any) -> Any:
    if isinstance(proof, Mapping):
        return proof.get(key, default)
    return getattr(proof, key, default)
