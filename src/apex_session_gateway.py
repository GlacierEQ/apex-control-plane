"""Source-bound APEX session gateway for an explicitly controlled model host.

The host MUST invoke this function; it is not a native ChatGPT boot or memory
consolidation interceptor. Reuses Spiral -> APEX's authenticated admission and
requires provider-backed callbacks for reservation, persistence, and readback.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Callable

@dataclass(frozen=True)
class Recovery:
    """Recovered context for one mission, supplied by the host journal."""

    mission_id: str
    source_ref: str
    cursor: str
    corrections: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    material_context_found: bool = False


@dataclass(frozen=True)
class ContextApplication:
    mission_id: str
    source_ref: str
    cursor: str
    corrections: tuple[str, ...]
    facts: tuple[str, ...]
    application_ref: str


@dataclass(frozen=True)
class AdmissionReceipt:
    mission_id: str
    chat_session_id: str
    source_ref: str
    cursor: str
    recovery: Recovery
    application_ref: str = ""
    application: Any = None


def execute_with_recovered_context(
    *,
    journal: Any,
    chat_session_id: str,
    kernel: Any,
    expected_mission_id: str,
    execute: Callable[[AdmissionReceipt], Any],
    apply_context: Callable[[Any], ContextApplication],
) -> Any:
    """Recover, apply, then execute -- all from host-supplied objects.

    The journal supplies recovery through a ``recover(session, mission)``
    method, a ``recovery`` attribute, or by being a Recovery itself.
    This replaces the deleted admission module with a local, minimal
    equivalent; it does not resurrect that module.
    """
    if isinstance(journal, Recovery):
        recovery = journal
    elif hasattr(journal, "recover"):
        recovery = journal.recover(chat_session_id, expected_mission_id)
    elif hasattr(journal, "recovery"):
        recovery = journal.recovery
    else:
        raise GatewayDenied("journal supplies no recoverable context")
    if not isinstance(recovery, Recovery):
        raise GatewayDenied("recovered context must be a Recovery")
    if recovery.mission_id != expected_mission_id:
        raise GatewayDenied("recovered context belongs to a different mission; not the requested mission")
    if not callable(apply_context):
        raise GatewayDenied("context application callback required")
    application = apply_context(recovery)
    if not isinstance(application, ContextApplication):
        raise GatewayDenied("context application must be a ContextApplication")
    if (not isinstance(application.application_ref, str)
            or not application.application_ref.strip()
            or application.mission_id != recovery.mission_id
            or application.source_ref != recovery.source_ref
            or application.cursor != recovery.cursor
            or not isinstance(application.corrections, tuple)
            or not isinstance(application.facts, tuple)
            or application.corrections != recovery.corrections
            or application.facts != recovery.facts):
        raise GatewayDenied("source-matched context application receipt required")
    receipt = AdmissionReceipt(
        mission_id=recovery.mission_id,
        chat_session_id=chat_session_id,
        source_ref=recovery.source_ref,
        cursor=recovery.cursor,
        recovery=recovery,
        application_ref=application.application_ref,
        application=application,
    )
    return execute(receipt)


class GatewayDenied(RuntimeError):
    """The host cannot certify provenance or durable continuation."""


@dataclass(frozen=True)
class OriginRecord:
    """Exact original bytes and their independently provided speaker identity."""
    speaker: str
    original_bytes: bytes


@dataclass(frozen=True)
class SourceAssertion:
    source_ref: str
    speaker: str
    verbatim: str
    start_byte: int
    end_byte: int
    source_sha256: str


@dataclass(frozen=True)
class MemoryProposal:
    kind: str
    source: SourceAssertion


@dataclass(frozen=True)
class GatewayModelOutput:
    text: str
    attributions: tuple[SourceAssertion, ...]
    memory_proposals: tuple[MemoryProposal, ...]
    corrections_applied: tuple[str, ...]


@dataclass(frozen=True)
class ContinuationEnvelope:
    operation_key: str
    chat_session_id: str
    mission_id: str
    source_ref: str
    cursor: str
    corrections: tuple[str, ...]
    response_text: str
    attributions: tuple[SourceAssertion, ...]
    memory_proposals: tuple[MemoryProposal, ...]
    digest: str
    # Explicitly mark model-authored output and non-authoritative memory candidates.
    # A downstream consumer must never interpret either as Operator-authored fact.
    response_author: str = "assistant"
    memory_authority: str = "SOURCE_CANDIDATE_ONLY"


_USER_AUTHORITY_KINDS = frozenset({
    "user_instruction", "user_fact", "user_correction", "user_preference",
})
_MANUAL_ADOPTION_KINDS = frozenset({
    "user_instruction", "user_fact", "user_preference",
})
_AUTOMATIC_SOURCE_CANDIDATE_KINDS = frozenset({
    "user_correction", "source_quote", "assistant_inference",
})


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatewayDenied(f"{label} must be nonempty text")
    return value


def _verify_assertion(
    assertion: SourceAssertion, resolve_source: Callable[[str], OriginRecord]
) -> None:
    if not isinstance(assertion, SourceAssertion):
        raise GatewayDenied("attribution must have an original-source assertion")
    ref = _required_text(assertion.source_ref, "original source ref")
    if assertion.speaker not in ("user", "assistant", "other"):
        raise GatewayDenied("source speaker must be explicitly user, assistant or other")
    if not isinstance(assertion.verbatim, str) or not assertion.verbatim.strip():
        raise GatewayDenied("verbatim source statement required")
    if (not isinstance(assertion.start_byte, int)
            or isinstance(assertion.start_byte, bool)
            or not isinstance(assertion.end_byte, int)
            or isinstance(assertion.end_byte, bool)
            or assertion.start_byte < 0
            or assertion.end_byte <= assertion.start_byte):
        raise GatewayDenied("invalid source byte span")
    if not isinstance(assertion.source_sha256, str):
        raise GatewayDenied("original digest missing")
    try:
        source = resolve_source(ref)
    except Exception as exc:
        raise GatewayDenied("original source readback failed") from exc
    if not isinstance(source, OriginRecord) or not isinstance(source.original_bytes, bytes):
        raise GatewayDenied("source readback requires original bytes and speaker")
    if source.speaker != assertion.speaker:
        raise GatewayDenied("source speaker does not match original record")
    actual = "sha256:" + sha256(source.original_bytes).hexdigest()
    if assertion.source_sha256 != actual:
        raise GatewayDenied("original source digest mismatch")
    if assertion.end_byte > len(source.original_bytes):
        raise GatewayDenied("source byte span out of bounds")
    span = source.original_bytes[assertion.start_byte:assertion.end_byte]
    if span != assertion.verbatim.encode("utf-8"):
        raise GatewayDenied("source text does not match original byte span")


def _validate_output(
    output: GatewayModelOutput,
    receipt: AdmissionReceipt,
    resolve_source: Callable[[str], OriginRecord],
) -> None:
    if not isinstance(output, GatewayModelOutput):
        raise GatewayDenied("model must produce a structured gateway output")
    _required_text(output.text, "response text")
    if not isinstance(output.attributions, tuple) or not isinstance(output.memory_proposals, tuple):
        raise GatewayDenied("attributions and proposals must be immutable tuples")
    if (not isinstance(output.corrections_applied, tuple)
            or output.corrections_applied != tuple(receipt.recovery.corrections)):
        raise GatewayDenied("recovered corrections were omitted or modified")
    checked: set[SourceAssertion] = set()
    for assertion in output.attributions:
        _verify_assertion(assertion, resolve_source)
        checked.add(assertion)
    for proposal in output.memory_proposals:
        if not isinstance(proposal, MemoryProposal):
            raise GatewayDenied("memory promotion must carry a typed source proposal")
        _required_text(proposal.kind, "memory kind")
        if proposal.source not in checked:
            _verify_assertion(proposal.source, resolve_source)
        if proposal.kind in _USER_AUTHORITY_KINDS and proposal.source.speaker != "user":
            raise GatewayDenied("user-originated source required for user direction or memory")
        if proposal.kind in _MANUAL_ADOPTION_KINDS:
            # A quote from the user is NOT authority for an LLM to infer that it
            # is an instruction/fact/preference. In particular, a negated
            # correction must never be inverted into an adopted direction.
            # An explicitly authenticated Operator adoption path is required.
            raise GatewayDenied("explicit authority required for memory classification")
        if proposal.kind not in _AUTOMATIC_SOURCE_CANDIDATE_KINDS:
            raise GatewayDenied("unsupported memory kind; use source-only candidate")
        if proposal.kind == "assistant_inference" and proposal.source.speaker != "assistant":
            raise GatewayDenied("assistant inference must have assistant provenance")
        # All proposals remain untrusted, source-only candidates. No model-authored
        # proposal is a governing user instruction or an accepted factual memory.


def _snapshot(envelope: ContinuationEnvelope) -> dict[str, Any]:
    return {
        "operation_key": envelope.operation_key,
        "chat_session_id": envelope.chat_session_id,
        "mission_id": envelope.mission_id,
        "source_ref": envelope.source_ref,
        "cursor": envelope.cursor,
        "corrections": list(envelope.corrections),
        "response_text": envelope.response_text,
        "response_author": envelope.response_author,
        "memory_authority": envelope.memory_authority,
        "attributions": [vars(item) for item in envelope.attributions],
        "memory_proposals": [
            {"kind": item.kind, "source": vars(item.source)}
            for item in envelope.memory_proposals
        ],
    }


def _envelope_digest(envelope: ContinuationEnvelope) -> str:
    canonical = json.dumps(
        _snapshot(envelope), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def run_admitted_session(
    *,
    journal: Any,
    chat_session_id: str,
    kernel: Any,
    expected_mission_id: str,
    invocation_id: str,
    apply_context: Callable[[Any], ContextApplication],
    invoke_model: Callable[[AdmissionReceipt], GatewayModelOutput],
    resolve_source: Callable[[str], OriginRecord],
    reserve: Callable[[str], bool],
    persist: Callable[[ContinuationEnvelope], Any],
    readback: Callable[[Any], ContinuationEnvelope],
) -> GatewayModelOutput:
    """Admit -> reserve -> invoke -> validate -> persist -> independent readback.

    Host-provided callbacks are not authenticated automatically. This gateway
    only certifies equivalence to the supplied original-source resolver/store;
    the host must provide an independently authenticated resolver, an atomic
    durable reservation, and an independent persistent-store readback.
    """
    for name, callback in {
        "apply_context": apply_context, "invoke_model": invoke_model,
        "resolve_source": resolve_source, "reserve": reserve,
        "persist": persist, "readback": readback,
    }.items():
        if not callable(callback):
            raise GatewayDenied("all gateway callbacks are required: " + name)
    mission = _required_text(expected_mission_id, "expected mission identity")
    turn = _required_text(invocation_id, "invocation identity")
    session = _required_text(chat_session_id, "chat session identity")
    if any(":" in part for part in (mission, turn, session)):
        raise GatewayDenied("ambiguous operation identity component")

    def after_admission(receipt: AdmissionReceipt) -> GatewayModelOutput:
        # Reservation occurs BEFORE any potentially effectful model callback.
        # On failure the reservation stays reserved: a host must reconcile
        # provider state before retrying an uncertain invocation.
        key = ":".join((mission, "model", session, turn))
        try:
            reserved = reserve(key)
        except Exception as exc:
            raise GatewayDenied("durable reservation unavailable") from exc
        if reserved is not True:
            raise GatewayDenied("operation already reserved; reconcile before replay")
        output = invoke_model(receipt)
        _validate_output(output, receipt, resolve_source)
        envelope = ContinuationEnvelope(
            operation_key=key,
            chat_session_id=receipt.chat_session_id,
            mission_id=receipt.mission_id,
            source_ref=receipt.source_ref,
            cursor=receipt.cursor,
            corrections=tuple(receipt.recovery.corrections),
            response_text=output.text,
            attributions=output.attributions,
            memory_proposals=output.memory_proposals,
            digest="",
        )
        from dataclasses import replace
        envelope = replace(envelope, digest=_envelope_digest(envelope))
        try:
            checkpoint = persist(envelope)
            if checkpoint is None:
                raise GatewayDenied("no durable checkpoint was returned")
            persisted = readback(checkpoint)
        except GatewayDenied:
            raise
        except Exception as exc:
            raise GatewayDenied("continuation persistence or readback failed") from exc
        if not isinstance(persisted, ContinuationEnvelope):
            raise GatewayDenied("continuation readback missing typed envelope")
        if (persisted != envelope or persisted.digest != _envelope_digest(persisted)):
            raise GatewayDenied("continuation readback differs from admitted output")
        return output

    return execute_with_recovered_context(
        journal=journal, chat_session_id=session, kernel=kernel,
        expected_mission_id=mission, execute=after_admission,
        apply_context=apply_context,
    )
