"""Mission-scoped forward-frontier selection for the existing APEX outcome runtime.

The host must restore authentic owning-mission history from its existing
Spiral/APEX journal. This component never invokes a provider, grants external
authority, or makes native ChatGPT startup automatic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

SCHEMA = "glaciereq.apex.forward-frontier.v1"
STAGES = frozenset({"INTERMEDIATE", "NO_DELTA", "BLOCKED", "ATTEMPTED",
                    "VERIFIED_MATERIAL_DELTA", "HUMAN_OUTCOME"})
PROOF_STAGES = frozenset({"VERIFIED_MATERIAL_DELTA", "HUMAN_OUTCOME"})
ASSISTANT_PREFIXES = frozenset({"assistant", "artifact", "summary", "matrix",
                                "report", "ledger", "plan"})


def _ref(value: str, field: str) -> str:
    if not isinstance(value, str) or ":" not in value:
        raise ValueError(f"{field} requires kind:locator")
    kind, locator = value.split(":", 1)
    if not kind.strip() or not locator.strip():
        raise ValueError(f"{field} requires kind:locator")
    return value


@dataclass(frozen=True)
class ForwardAction:
    action_id: str
    method_id: str
    source_state_ref: str
    expected_benefit: int
    urgency: int
    authorized: bool = False
    external_effect: bool = False
    external_effect_authorized: bool = False
    already_completed: bool = False

    def __post_init__(self) -> None:
        for name in ("action_id", "method_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonempty")
        _ref(self.source_state_ref, "source_state_ref")
        for name in ("expected_benefit", "urgency"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in ("authorized", "external_effect", "external_effect_authorized", "already_completed"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")


@dataclass(frozen=True)
class ForwardReceipt:
    action_id: str
    method_id: str
    source_state_ref: str
    stage: str
    provider_ref: str
    after_state_ref: str | None = None
    readback_ref: str | None = None
    source_class: str = "provider"
    outcome_scope: str = "unclassified"

    def __post_init__(self) -> None:
        for name in ("action_id", "method_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonempty")
        _ref(self.source_state_ref, "source_state_ref")
        _ref(self.provider_ref, "provider_ref")
        if self.stage not in STAGES:
            raise ValueError(f"unrecognized stage: {self.stage}")
        if self.readback_ref is not None:
            _ref(self.readback_ref, "readback_ref")
        if self.after_state_ref is not None:
            _ref(self.after_state_ref, "after_state_ref")
        if self.stage in PROOF_STAGES:
            if self.source_class != "source_native":
                raise ValueError("mission-state promotion requires source_native proof")
            if not self.readback_ref:
                raise ValueError("mission-state promotion requires provider-native readback")
            if not self.after_state_ref or self.after_state_ref == self.source_state_ref:
                raise ValueError("mission-state promotion requires a distinct after-state")
            for ref in (self.provider_ref, self.readback_ref):
                if ref.split(":", 1)[0] in ASSISTANT_PREFIXES:
                    raise ValueError("assistant artifacts cannot prove mission outcomes")
        if self.stage == "HUMAN_OUTCOME" and self.outcome_scope not in {
            "unclassified", "contact", "protection", "welfare", "court_relief"
        }:
            raise ValueError("invalid outcome scope")


@dataclass(frozen=True)
class ForwardChoice:
    status: str
    action_id: str | None
    method_id: str | None
    suppressed: Mapping[str, str]
    mission_complete: bool = False
    reason: str = ""


def choose_forward_action(
    mission_id: str,
    candidates: Sequence[ForwardAction],
    history: Sequence[ForwardReceipt] = (),
) -> ForwardChoice:
    """Select highest-benefit authorized fresh work without global stop semantics.

    Identical action/method/source-state retries are suppressed; a changed lawful
    method or material source state reopens the candidate. Exhaustion of these
    candidate routes NEVER establishes mission completion.
    """
    _ref(mission_id, "mission_id")
    previous = {(r.action_id, r.method_id, r.source_state_ref): r for r in history}
    eligible: list[ForwardAction] = []
    suppressed: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()
    for action in candidates:
        key = (action.action_id, action.method_id, action.source_state_ref)
        if key in seen:
            suppressed[action.action_id] = "duplicate candidate in current mission tree"
            continue
        seen.add(key)
        if action.already_completed:
            suppressed[action.action_id] = "completed work is not a fresh frontier"
        elif not action.authorized:
            suppressed[action.action_id] = "operator has not authorized this action"
        elif action.external_effect and not action.external_effect_authorized:
            suppressed[action.action_id] = "external effects require separate operator authorization"
        elif key in previous:
            suppressed[action.action_id] = (
                f"unchanged previous {previous[key].stage.lower()} route; "
                "new material state or different lawful method required"
            )
        else:
            eligible.append(action)
    if not eligible:
        return ForwardChoice(
            "NO_AUTHORIZED_FRESH_ROUTE", None, None, suppressed, False,
            "Do not claim closure; diagnose and discover another authorized material route.",
        )
    eligible.sort(key=lambda a: (-a.expected_benefit, -a.urgency, a.action_id, a.method_id))
    chosen = eligible[0]
    return ForwardChoice(
        "EXECUTE", chosen.action_id, chosen.method_id, suppressed, False,
        "Advance, verify actual effect, then preserve exact source-bound continuation.",
    )


@dataclass
class ForwardLedger:
    """A projection of the existing mission journal; not a replacement store."""
    mission_id: str
    receipts: list[ForwardReceipt] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ref(self.mission_id, "mission_id")
        if not isinstance(self.receipts, list) or not all(
            isinstance(receipt, ForwardReceipt) for receipt in self.receipts
        ):
            raise ValueError("receipts must contain typed ForwardReceipt entries")

    def record(self, receipt: ForwardReceipt) -> None:
        identity = (receipt.action_id, receipt.method_id, receipt.source_state_ref,
                    receipt.stage, receipt.provider_ref)
        if any((r.action_id, r.method_id, r.source_state_ref, r.stage, r.provider_ref)
               == identity for r in self.receipts):
            return
        self.receipts.append(receipt)

    def choose(self, candidates: Sequence[ForwardAction]) -> ForwardChoice:
        return choose_forward_action(self.mission_id, candidates, self.receipts)

    @property
    def human_outcomes(self) -> int:
        return sum(r.stage == "HUMAN_OUTCOME" for r in self.receipts)

    @property
    def mission_outcomes(self) -> int:
        return self.human_outcomes

    @property
    def current_contact_state(self) -> str:
        if any(r.stage == "HUMAN_OUTCOME" and r.outcome_scope == "contact"
               for r in self.receipts):
            return "VERIFIED_CONTACT_EVENT"
        return "NOT_CHECKED"  # A bounded search is not proof of zero events.

    def snapshot(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "mission_id": self.mission_id,
                "receipts": [asdict(receipt) for receipt in self.receipts]}

    @classmethod
    def from_snapshot(cls, data: Mapping[str, Any], *, expected_mission_id: str) -> "ForwardLedger":
        _ref(expected_mission_id, "expected_mission_id")
        if not isinstance(data, Mapping) or data.get("schema") != SCHEMA:
            raise ValueError("invalid forward-frontier journal schema")
        if data.get("mission_id") != expected_mission_id:
            raise ValueError("journal mission does not match authenticated active mission")
        raw = data.get("receipts")
        if not isinstance(raw, list):
            raise ValueError("journal requires an authenticated receipt list")
        try:
            return cls(expected_mission_id, [ForwardReceipt(**entry) for entry in raw])
        except (TypeError, KeyError) as exc:
            raise ValueError("malformed forward-frontier journal") from exc
