"""APEX execution-uplift runtime kernel.

The kernel preserves truthful lifecycle state, receipts, instruction fidelity,
provider readback, and repairability without turning those quality mechanisms
into generalized permission authority.

Core objective:
    capability -> execute -> test -> harden -> verify -> repair -> persist ->
    read back -> complete truthfully

A failed quality signal moves the affected task into REPAIRING. A concrete
provider/credential/destructive boundary may still use BLOCKED for that route.
Startup observer findings never veto kernel construction by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from uuid import uuid4

from apex_enforced_startup import get_in_process_apex_validation
from notion_continuity_gate import get_in_process_notion_validation
from operator_fidelity_lock import get_in_process_operator_fidelity_lock
from operator_fidelity_preflight import get_in_process_operator_fidelity_validation
from prime_directive_boot import get_in_process_boot_validation


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "apex_runtime_policy.json"
_FACTORY_SEAL = object()
EXPECTED_STARTUP_OBSERVERS = (
    "notion_continuity",
    "prime_directive",
    "operator_fidelity_lock",
    "operator_fidelity",
    "apex_startup",
)
_DESTRUCTIVE_OPERATION = re.compile(
    r"(?i)(?:^|[_\-. ])(delete|destroy|purge|wipe|revoke|drop|force[_\- ]?push)(?:$|[_\-. ])"
)


class RuntimeViolation(RuntimeError):
    """Raised for malformed requests or genuine impossible runtime transitions."""


class RuntimePhase(str, Enum):
    BOOTSTRAPPED = "bootstrapped"
    CONTEXT_RECOVERING = "context_recovering"
    READY = "ready"
    OBSERVING = "observing"
    EXECUTING = "executing"
    TESTING = "testing"
    ADVERSARIAL_TESTING = "adversarial_testing"
    REPAIRING = "repairing"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    PERSISTING = "persisting"
    READBACK = "readback"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class TaskMode(str, Enum):
    OBSERVATION = "observation"
    MUTATION = "mutation"


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    kind: str
    reference: str
    recorded_at: datetime
    successful: bool
    details_sha256: str

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("receipt.kind is required")
        _require_receipt_ref(self.reference)
        if self.recorded_at.tzinfo is None:
            raise ValueError("receipt.recorded_at must be timezone-aware")
        if not _is_sha256(self.details_sha256):
            raise ValueError("receipt.details_sha256 must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    runtime_id: str
    phase: str
    task_id: str | None
    mode: str | None
    operation_class: str | None
    action_scope: str | None
    target_state: str | None
    instruction_sha256: str | None
    receipt_kinds: tuple[str, ...]
    unresolved_blockers: tuple[str, ...]
    verified_gain_refs: tuple[str, ...]
    completed_task_count: int
    startup_gates: tuple[str, ...]
    startup_findings: tuple[str, ...] = ()
    repair_reasons: tuple[str, ...] = ()


@dataclass(slots=True)
class _TaskState:
    task_id: str
    literal_instruction: str = field(repr=False)
    instruction_sha256: str
    target_state: str
    operation_class: str
    mode: TaskMode
    action_scope: str
    operator_authorization_ref: str | None
    prior_state_ref: str | None
    source_refs: tuple[str, ...]
    verification_plan: tuple[str, ...]
    receipts: list[RuntimeReceipt] = field(default_factory=list)
    verified_gain_refs: list[str] = field(default_factory=list)
    unresolved_blockers: list[str] = field(default_factory=list)
    repair_reasons: list[str] = field(default_factory=list)
    resume_phase: RuntimePhase | None = None


@dataclass(slots=True)
class ApexRuntimeKernel:
    """Single-owner repair-forward lifecycle kernel for one active task."""

    policy: Mapping[str, Any]
    startup_gates: tuple[str, ...]
    _seal: object = field(repr=False)
    startup_findings: tuple[str, ...] = ()
    runtime_id: str = field(default_factory=lambda: str(uuid4()))
    phase: RuntimePhase = RuntimePhase.BOOTSTRAPPED
    _task: _TaskState | None = field(default=None, repr=False)
    _history: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _audit: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _sequence: int = 0

    def __post_init__(self) -> None:
        if self._seal is not _FACTORY_SEAL:
            raise TypeError("ApexRuntimeKernel must be created by verified factory")
        _validate_policy(self.policy)
        self._audit_event("runtime_bootstrapped")
        for finding in self.startup_findings:
            self._audit_event("startup_uplift_finding")

    @property
    def task(self) -> _TaskState:
        if self._task is None:
            raise RuntimeViolation("no task is bound to the runtime")
        return self._task

    def bind_task(
        self,
        *,
        literal_instruction: str,
        target_state: str,
        operation_class: str,
        mode: str | TaskMode,
        action_scope: str,
        operator_authorization_ref: str | None = None,
        prior_state_ref: str | None = None,
        source_refs: Sequence[str] = (),
        verification_plan: Sequence[str] = (),
    ) -> RuntimeSnapshot:
        """Bind exact task intent; routine mutation needs no extra permission token."""
        if self.phase not in {RuntimePhase.BOOTSTRAPPED, RuntimePhase.COMPLETE}:
            raise RuntimeViolation(
                f"cannot bind a new task while runtime phase is {self.phase.value}"
            )
        if self.phase is RuntimePhase.COMPLETE and self._task is not None:
            self._archive_completed_task()

        instruction = _require_text(literal_instruction, "literal_instruction")
        target = _require_text(target_state, "target_state")
        operation = _require_text(operation_class, "operation_class")
        task_mode = TaskMode(mode)
        normalized_scope = _normalize_scope(action_scope)

        if task_mode is TaskMode.OBSERVATION and normalized_scope != "none":
            raise RuntimeViolation("observation mode requires action_scope=none")
        if task_mode is TaskMode.MUTATION and normalized_scope not in {"internal", "external"}:
            raise RuntimeViolation("mutation mode requires action_scope=internal or external")

        authority_ref = _optional_receipt_ref(operator_authorization_ref)
        if task_mode is TaskMode.MUTATION and _is_destructive_operation(operation):
            if authority_ref is None:
                raise RuntimeViolation(
                    "destructive or irreversible mutation requires scoped operator authority reference"
                )

        prior_ref = _optional_receipt_ref(prior_state_ref)
        refs = tuple(_validated_receipt_refs(source_refs))
        plan = tuple(
            _require_text(step, "verification_plan step")
            for step in verification_plan
        )
        if not plan:
            plan = (
                "verify operation-specific postconditions",
                "read back provider or target state",
                "repair any mismatch and reverify",
            )

        self._task = _TaskState(
            task_id=str(uuid4()),
            literal_instruction=instruction,
            instruction_sha256=_digest_text(instruction),
            target_state=target,
            operation_class=operation,
            mode=task_mode,
            action_scope=normalized_scope,
            operator_authorization_ref=authority_ref,
            prior_state_ref=prior_ref,
            source_refs=refs,
            verification_plan=plan,
        )
        self.phase = RuntimePhase.CONTEXT_RECOVERING
        self._audit_event("task_bound")
        return self.snapshot()

    def record_context_recovery(
        self,
        reference: str,
        *,
        recovered_refs: Sequence[str],
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        """Record recovered prior/current context before any task work begins."""
        self._require_phase(RuntimePhase.CONTEXT_RECOVERING)
        refs = tuple(_validated_receipt_refs(recovered_refs))
        if not refs:
            raise RuntimeViolation(
                "context recovery requires at least one recovered source reference"
            )
        self.task.source_refs = tuple(dict.fromkeys((*self.task.source_refs, *refs)))
        self._record_receipt("context_recovery", reference, True, details)
        self.phase = RuntimePhase.READY
        self._audit_event("context_recovered")
        return self.snapshot()

    def begin(self) -> RuntimeSnapshot:
        self._require_phase(RuntimePhase.READY)
        self.phase = (
            RuntimePhase.OBSERVING
            if self.task.mode is TaskMode.OBSERVATION
            else RuntimePhase.EXECUTING
        )
        self._audit_event("task_started")
        return self.snapshot()

    def record_observation(
        self,
        reference: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_mode(TaskMode.OBSERVATION)
        self._require_phase(RuntimePhase.OBSERVING)
        self._record_receipt("observation", reference, True, details)
        self.phase = RuntimePhase.VERIFYING
        self._audit_event("observation_recorded")
        return self.snapshot()

    def record_execution(
        self,
        reference: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_mode(TaskMode.MUTATION)
        self._require_phase(RuntimePhase.EXECUTING)
        self._record_receipt("execution", reference, True, details)
        self.phase = RuntimePhase.TESTING
        self._audit_event("execution_recorded")
        return self.snapshot()

    def record_test(
        self,
        reference: str,
        *,
        passed: bool,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_mode(TaskMode.MUTATION)
        self._require_phase(RuntimePhase.TESTING)
        self._record_receipt("test", reference, passed, details)
        if passed:
            self.phase = RuntimePhase.ADVERSARIAL_TESTING
            self._audit_event("test_passed")
        else:
            self._enter_repair("test_failed")
        return self.snapshot()

    def record_adversarial_test(
        self,
        reference: str,
        *,
        passed: bool,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_mode(TaskMode.MUTATION)
        self._require_phase(RuntimePhase.ADVERSARIAL_TESTING)
        self._record_receipt("adversarial_test", reference, passed, details)
        if passed:
            self.phase = RuntimePhase.VERIFYING
            self._audit_event("adversarial_test_passed")
        else:
            self._enter_repair("adversarial_test_failed")
        return self.snapshot()

    def record_repair(
        self,
        reference: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_phase(RuntimePhase.REPAIRING)
        self._record_receipt("repair", reference, True, details)
        self.task.repair_reasons.clear()
        self.phase = (
            RuntimePhase.VERIFYING
            if self.task.mode is TaskMode.OBSERVATION
            else RuntimePhase.TESTING
        )
        self._audit_event("repair_recorded")
        return self.snapshot()

    def record_verification(
        self,
        reference: str,
        *,
        passed: bool,
        verified_gain_refs: Sequence[str] = (),
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_phase(RuntimePhase.VERIFYING)
        self._record_receipt("verification", reference, passed, details)
        if not passed:
            self._enter_repair("verification_failed")
            return self.snapshot()

        gains = tuple(_validated_receipt_refs(verified_gain_refs))
        if self.task.mode is TaskMode.MUTATION and not gains:
            self._enter_repair("verified_gain_reference_missing")
            return self.snapshot()

        self.task.verified_gain_refs.extend(
            ref for ref in gains if ref not in self.task.verified_gain_refs
        )
        self.phase = (
            RuntimePhase.READBACK
            if self.task.mode is TaskMode.OBSERVATION
            else RuntimePhase.VERIFIED
        )
        self._audit_event("verification_passed")
        return self.snapshot()

    def begin_persistence(self) -> RuntimeSnapshot:
        self._require_mode(TaskMode.MUTATION)
        self._require_phase(RuntimePhase.VERIFIED)
        self.phase = RuntimePhase.PERSISTING
        self._audit_event("persistence_started")
        return self.snapshot()

    def record_persistence(
        self,
        reference: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_mode(TaskMode.MUTATION)
        self._require_phase(RuntimePhase.PERSISTING)
        self._record_receipt("persistence", reference, True, details)
        self.phase = RuntimePhase.READBACK
        self._audit_event("persistence_recorded")
        return self.snapshot()

    def record_readback(
        self,
        reference: str,
        *,
        matches_expected_state: bool,
        target_reached: bool,
        details: Mapping[str, Any] | None = None,
    ) -> RuntimeSnapshot:
        self._require_phase(RuntimePhase.READBACK)
        successful = bool(matches_expected_state and target_reached)
        self._record_receipt("readback", reference, successful, details)
        if not successful:
            reason = "readback_mismatch" if not matches_expected_state else "target_not_reached"
            self._enter_repair(reason)
            return self.snapshot()

        missing = self._completion_gaps()
        if missing:
            self._enter_repair("completion_evidence_gap:" + ",".join(missing))
            return self.snapshot()

        self.phase = RuntimePhase.COMPLETE
        self._audit_event("task_complete")
        return self.snapshot()

    def block(self, reason: str, *, reference: str) -> RuntimeSnapshot:
        """Record a concrete route-local provider/credential/destructive boundary."""
        reason_text = _require_text(reason, "blocker reason")
        _require_receipt_ref(reference)
        if self.phase is RuntimePhase.COMPLETE:
            raise RuntimeViolation("completed task cannot be retroactively blocked")
        if self.phase is not RuntimePhase.BLOCKED:
            self.task.resume_phase = self.phase
        if reason_text not in self.task.unresolved_blockers:
            self.task.unresolved_blockers.append(reason_text)
        self._record_receipt("blocker", reference, False, {"reason": reason_text})
        self.phase = RuntimePhase.BLOCKED
        self._audit_event("route_blocked")
        return self.snapshot()

    def resolve_blocker(
        self,
        reason: str,
        *,
        resolution_reference: str,
    ) -> RuntimeSnapshot:
        self._require_phase(RuntimePhase.BLOCKED)
        reason_text = _require_text(reason, "blocker reason")
        if reason_text not in self.task.unresolved_blockers:
            raise RuntimeViolation("specified blocker is not unresolved")
        self._record_receipt("blocker_resolution", resolution_reference, True, None)
        self.task.unresolved_blockers.remove(reason_text)
        if self.task.unresolved_blockers:
            self._audit_event("blocker_partially_resolved")
            return self.snapshot()

        resume = self.task.resume_phase or RuntimePhase.READY
        if resume is RuntimePhase.BLOCKED:
            resume = RuntimePhase.READY
        self.task.resume_phase = None
        self.phase = resume
        self._audit_event("blocker_resolved")
        return self.snapshot()

    def assert_instruction_fidelity(self, literal_instruction: str) -> None:
        supplied = _require_text(literal_instruction, "literal_instruction")
        if _digest_text(supplied) != self.task.instruction_sha256:
            raise RuntimeViolation("literal Operator instruction drift detected")

    def snapshot(self) -> RuntimeSnapshot:
        task = self._task
        return RuntimeSnapshot(
            runtime_id=self.runtime_id,
            phase=self.phase.value,
            task_id=task.task_id if task else None,
            mode=task.mode.value if task else None,
            operation_class=task.operation_class if task else None,
            action_scope=task.action_scope if task else None,
            target_state=task.target_state if task else None,
            instruction_sha256=task.instruction_sha256 if task else None,
            receipt_kinds=tuple(receipt.kind for receipt in task.receipts) if task else (),
            unresolved_blockers=tuple(task.unresolved_blockers) if task else (),
            verified_gain_refs=tuple(task.verified_gain_refs) if task else (),
            completed_task_count=len(self._history),
            startup_gates=self.startup_gates,
            startup_findings=self.startup_findings,
            repair_reasons=tuple(task.repair_reasons) if task else (),
        )

    def receipts(self) -> tuple[RuntimeReceipt, ...]:
        return tuple(self.task.receipts)

    def audit_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(event) for event in self._audit)

    def _archive_completed_task(self) -> None:
        if self.phase is not RuntimePhase.COMPLETE:
            raise RuntimeViolation("only completed tasks may be archived")
        task = self.task
        self._history.append(
            {
                "task_id": task.task_id,
                "instruction_sha256": task.instruction_sha256,
                "target_state_sha256": _digest_text(task.target_state),
                "operation_class": task.operation_class,
                "mode": task.mode.value,
                "receipt_kinds": tuple(receipt.kind for receipt in task.receipts),
                "verified_gain_count": len(task.verified_gain_refs),
            }
        )

    def _record_receipt(
        self,
        kind: str,
        reference: str,
        successful: bool,
        details: Mapping[str, Any] | None,
    ) -> RuntimeReceipt:
        _require_receipt_ref(reference)
        payload = dict(details or {})
        receipt = RuntimeReceipt(
            kind=kind,
            reference=reference,
            recorded_at=datetime.now(UTC),
            successful=bool(successful),
            details_sha256=_digest_json(payload),
        )
        self.task.receipts.append(receipt)
        return receipt

    def _completion_gaps(self) -> list[str]:
        gaps: list[str] = []
        if self.task.unresolved_blockers:
            gaps.append("unresolved_route_constraints")
        required = self.policy["receipt_requirements"][self.task.mode.value]
        successful_kinds = {
            receipt.kind for receipt in self.task.receipts if receipt.successful
        }
        gaps.extend(kind for kind in required if kind not in successful_kinds)
        if self.task.mode is TaskMode.MUTATION and not self.task.verified_gain_refs:
            gaps.append("verified_gain")
        return list(dict.fromkeys(gaps))

    def _enter_repair(self, reason: str) -> None:
        if reason not in self.task.repair_reasons:
            self.task.repair_reasons.append(reason)
        self.phase = RuntimePhase.REPAIRING
        self._audit_event("repair_required")

    def _require_mode(self, mode: TaskMode) -> None:
        if self.task.mode is not mode:
            raise RuntimeViolation(
                f"operation requires mode={mode.value}; active mode={self.task.mode.value}"
            )

    def _require_phase(self, *allowed: RuntimePhase) -> None:
        if self.phase not in allowed:
            values = ", ".join(item.value for item in allowed)
            raise RuntimeViolation(
                f"runtime phase {self.phase.value} cannot perform this operation; expected one of: {values}"
            )

    def _audit_event(self, event_type: str) -> None:
        self._sequence += 1
        event = {
            "sequence": self._sequence,
            "recorded_at": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "runtime_id": self.runtime_id,
            "phase": self.phase.value,
        }
        if self._task is not None:
            event["task_id"] = self._task.task_id
            event["instruction_sha256"] = self._task.instruction_sha256
        self._audit.append(event)


def load_runtime_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeViolation(f"APEX runtime policy not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeViolation(f"invalid APEX runtime policy JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeViolation("APEX runtime policy must be a JSON object")
    _validate_policy(payload)
    return payload


def create_verified_runtime_kernel(
    policy: Mapping[str, Any] | None = None,
) -> ApexRuntimeKernel:
    """Create a live kernel and attach startup observer findings for later repair."""
    gate_values = (
        ("notion_continuity", get_in_process_notion_validation()),
        ("prime_directive", get_in_process_boot_validation()),
        ("operator_fidelity_lock", get_in_process_operator_fidelity_lock()),
        ("operator_fidelity", get_in_process_operator_fidelity_validation()),
        ("apex_startup", get_in_process_apex_validation()),
    )
    findings: list[str] = []
    for name, validation in gate_values:
        if validation is None:
            findings.append(f"{name}: validation missing")
            continue
        if getattr(validation, "ok", None) is not True:
            findings.append(f"{name}: ok is not true")
        status = getattr(validation, "status", None)
        if status != "complete":
            findings.append(f"{name}: status={status!r}")

    return ApexRuntimeKernel(
        policy=dict(policy or load_runtime_policy()),
        startup_gates=EXPECTED_STARTUP_OBSERVERS,
        startup_findings=tuple(dict.fromkeys(findings)),
        _seal=_FACTORY_SEAL,
    )


def _validate_policy(policy: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "objective",
        "receipt_requirements",
        "action_scopes",
        "privacy",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise RuntimeViolation("APEX runtime policy missing: " + ", ".join(missing))

    if policy.get("objective") != "maximum_coherent_advance":
        raise RuntimeViolation("APEX runtime objective must remain maximum_coherent_advance")
    semantics = str(policy.get("execution_semantics", "")).strip()
    if semantics and semantics != "execute_harden_verify_repair_complete_receipt":
        raise RuntimeViolation("unsupported APEX execution_semantics")
    if policy.get("fail_closed") is True and semantics:
        raise RuntimeViolation(
            "fail_closed cannot retain authority under execution-uplift semantics"
        )

    configured = tuple(
        str(value).strip()
        for value in policy.get(
            "startup_observers", policy.get("required_startup_gates", ())
        )
    )
    if set(configured) != set(EXPECTED_STARTUP_OBSERVERS):
        raise RuntimeViolation("APEX runtime startup observer set is incomplete")

    requirements = policy.get("receipt_requirements")
    if not isinstance(requirements, Mapping):
        raise RuntimeViolation("receipt_requirements must be an object")
    expected = {
        "observation": {"context_recovery", "observation", "verification", "readback"},
        "mutation": {
            "context_recovery",
            "execution",
            "test",
            "adversarial_test",
            "verification",
            "persistence",
            "readback",
        },
    }
    for mode, required_kinds in expected.items():
        values = requirements.get(mode)
        if not isinstance(values, list) or set(values) != required_kinds:
            raise RuntimeViolation(
                f"receipt_requirements.{mode} must contain the full evidence set"
            )

    scopes = set(policy.get("action_scopes", ()))
    if scopes != {"none", "internal", "external"}:
        raise RuntimeViolation("action_scopes must be none, internal, external")

    privacy = policy.get("privacy")
    if not isinstance(privacy, Mapping):
        raise RuntimeViolation("privacy must be an object")
    if privacy.get("audit_literal_instruction") is not False:
        raise RuntimeViolation("runtime audit must not store literal instructions")
    if privacy.get("audit_tool_payloads") is not False:
        raise RuntimeViolation("runtime audit must not store tool payloads")


def _is_destructive_operation(operation_class: str) -> bool:
    normalized = str(operation_class).replace("/", "_")
    return _DESTRUCTIVE_OPERATION.search(normalized) is not None


def _normalize_scope(value: str) -> str:
    scope = _require_text(value, "action_scope").strip().lower()
    if scope not in {"none", "internal", "external"}:
        raise RuntimeViolation("action_scope must be none, internal, or external")
    return scope


def _validated_receipt_refs(values: Sequence[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        _require_receipt_ref(value)
        output.append(value)
    return output


def _optional_receipt_ref(value: str | None) -> str | None:
    if value is None:
        return None
    _require_receipt_ref(value)
    return value


def _require_receipt_ref(value: str | None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeViolation("receipt reference is required")
    prefix, separator, locator = value.strip().partition(":")
    if not separator or not prefix.strip() or not locator.strip():
        raise RuntimeViolation("receipt reference must use provider-or-kind:locator form")


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeViolation(f"{field_name} must be non-empty")
    return value.strip()


def _digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
