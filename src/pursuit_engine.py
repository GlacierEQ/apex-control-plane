"""Evidence-driven pursuit bridge for APEX/DOCKETS/Jack.

This does not impose sanctions, infer character, or originate provider effects.
It turns a source-bound individual finding into the next lawful accountability
operation. A hypothetical defense never downgrades authenticated observation.
Actual effects go through the existing APEX connector admission/idempotency and
provider-native continuation gate; this module creates no parallel case state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Callable

from .connector_mission_router import (
    ConnectorCapability, MissionAdmission, dispatch_once,
)


class PursuitViolation(ValueError):
    """Pursuit evidence, actor, duty or effect authorization was not established."""


class PursuitStage(str, Enum):
    AUTHENTICATE = "authenticate_observation"
    ESTABLISH_DUTY = "establish_governing_duty"
    IDENTIFY_ACTOR = "identify_accountable_actor"
    REQUEST_ACCOUNT = "request_specific_account"
    REASSESS = "reassess_with_verified_counterevidence"
    VERIFY_DISPOSITION = "verify_agency_disposition"
    FIND_LAWFUL_ROUTE = "find_independent_review_route"
    INDEPENDENT_REVIEW = "request_independent_review"
    COMPLETE = "verified_target_result"


@dataclass(frozen=True, slots=True)
class Counterclaim:
    proposition: str
    asserted_by: str
    supporting_refs: tuple[str, ...] = ()
    independently_verified: bool = False

    @property
    def evidence_backed(self) -> bool:
        return bool(self.supporting_refs and self.independently_verified)


@dataclass(frozen=True, slots=True)
class PursuitFinding:
    mission_id: str
    finding_id: str
    actor_id: str
    observation: str
    observation_ref: str
    observation_sha256: str
    observation_authenticated: bool
    duty_id: str
    duty_ref: str
    duty_verified: bool
    target: str
    counterclaims: tuple[Counterclaim, ...] = ()


@dataclass(frozen=True, slots=True)
class PursuitHistory:
    """Read from the owning provider and APEX journal, NEVER assistant claims."""

    challenge_receipt: str = ""
    agency_ack: str = ""
    response_window_elapsed: bool = False
    response_window_source: str = ""
    escalation_route: str = ""
    escalation_authorized: bool = False
    target_result_ref: str = ""
    target_result_readback: str = ""
    target_result_verified: bool = False
    assessed_counterclaim_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PursuitStep:
    mission_id: str
    finding_id: str
    actor_id: str
    stage: PursuitStage
    position: str
    evidence_refs: tuple[str, ...]
    adverse_claims_pending: tuple[str, ...]
    target: str
    outcome_verified: bool
    duty_verified: bool
    observation_authenticated: bool
    authorized_route: str = ""

    @property
    def operation_id(self) -> str:
        """Deterministic replay identity; stable within a finding and stage."""
        raw = "\x1f".join((self.mission_id, self.finding_id,
                             self.actor_id, self.stage.value, self.authorized_route))
        return "pursuit-" + sha256(raw.encode("utf-8")).hexdigest()[:32]


def _source_ref(value: str) -> bool:
    return isinstance(value, str) and ":" in value and all(value.split(":", 1))


def next_pursuit_step(finding: PursuitFinding, history: PursuitHistory) -> PursuitStep:
    """Advance to the next evidence-supported operation, never imaginary finality.

    history must be supplied by the owning durable case/receipt provider. An
    empty or unsupported opposing explanation cannot change authenticated facts.
    """
    if not all(isinstance(getattr(finding, attr), str) and getattr(finding, attr).strip()
               for attr in ("mission_id", "finding_id", "observation", "target")):
        raise PursuitViolation("mission, finding, observation and target required")
    if not isinstance(finding.observation_authenticated, bool) or not isinstance(finding.duty_verified, bool):
        raise PursuitViolation("verification flags must be explicit booleans")
    if (finding.observation_authenticated and
        (not _source_ref(finding.observation_ref) or
         len(finding.observation_sha256) != 64 or
         any(c not in "0123456789abcdef" for c in finding.observation_sha256))):
        raise PursuitViolation("authenticated fact requires native source reference and SHA256")
    if finding.duty_verified and (not finding.duty_id or not _source_ref(finding.duty_ref)):
        raise PursuitViolation("verified duty requires duty identity and source")
    if history.target_result_verified and (
        not _source_ref(history.target_result_ref) or
        not _source_ref(history.target_result_readback)):
        raise PursuitViolation("verified outcome requires native result and independent readback")
    refs = tuple(r for r in (finding.observation_ref, finding.duty_ref,
                             history.challenge_receipt, history.agency_ack,
                             history.response_window_source) if _source_ref(r))
    unsupported = tuple(c.proposition for c in finding.counterclaims if not c.evidence_backed)
    supported = tuple(c for c in finding.counterclaims if c.evidence_backed and
                      c.asserted_by == finding.actor_id and
                      any(r not in history.assessed_counterclaim_refs for r in c.supporting_refs))
    for c in supported:
        refs += tuple(r for r in c.supporting_refs if _source_ref(r))

    if history.target_result_verified:
        stage = PursuitStage.COMPLETE
    elif history.target_result_ref:
        stage = PursuitStage.VERIFY_DISPOSITION
    elif not finding.observation_authenticated:
        stage = PursuitStage.AUTHENTICATE
    elif not finding.duty_verified:
        stage = PursuitStage.ESTABLISH_DUTY
    elif not finding.actor_id.strip():
        stage = PursuitStage.IDENTIFY_ACTOR
    elif supported:
        stage = PursuitStage.REASSESS
    elif not history.challenge_receipt:
        stage = PursuitStage.REQUEST_ACCOUNT
    elif history.response_window_elapsed and _source_ref(history.response_window_source):
        stage = (PursuitStage.INDEPENDENT_REVIEW if
                 history.escalation_authorized and _source_ref(history.escalation_route)
                 else PursuitStage.FIND_LAWFUL_ROUTE)
    else:
        stage = PursuitStage.VERIFY_DISPOSITION

    return PursuitStep(
        mission_id=finding.mission_id,
        finding_id=finding.finding_id,
        actor_id=finding.actor_id,
        stage=stage,
        position=f"Authenticated observation: {finding.observation}. "
                 "Any distinct asserted review remains uncredited unless supported; "
                 "the observed fact survives all counterclaims.",
        evidence_refs=tuple(dict.fromkeys(refs)),
        adverse_claims_pending=unsupported,
        target=finding.target,
        outcome_verified=stage is PursuitStage.COMPLETE,
        duty_verified=finding.duty_verified,
        observation_authenticated=finding.observation_authenticated,
        authorized_route=history.escalation_route if stage is PursuitStage.INDEPENDENT_REVIEW else "",
    )


def dispatch_pursuit_step(
    step: PursuitStep, *, admission: MissionAdmission,
    capability: ConnectorCapability,
    reserve: Callable[[str], bool], execute: Callable[[], object],
    readback: Callable[[object], bool],
    persist_continuation: Callable[[object], object],
    verify_continuation: Callable[[object], bool],
) -> object:
    """Send only an admitted provider action through the existing APEX gate.

    The host supplies authenticated context, authorization, atomic reservation,
    native effect, independent readback and durable continuation. The provider
    receipt is NOT a completed human/legal outcome.
    """
    if step.stage not in {PursuitStage.REQUEST_ACCOUNT, PursuitStage.INDEPENDENT_REVIEW}:
        raise PursuitViolation("this stage cannot produce an external effect")
    if step.outcome_verified or not step.observation_authenticated or not step.duty_verified:
        raise PursuitViolation("an actionable source-backed finding is required")
    if step.mission_id != admission.expected_mission_id:
        raise PursuitViolation("pursuit step does not match expected host mission")
    if step.stage is PursuitStage.INDEPENDENT_REVIEW and not step.authorized_route:
        raise PursuitViolation("independent review requires a verified lawful route")
    return dispatch_once(
        admission, capability, step.operation_id, reserve, execute, readback,
        persist_continuation=persist_continuation,
        verify_continuation=verify_continuation,
    )
