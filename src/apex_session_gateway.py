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

from .chat_context_admission import (
    AdmissionReceipt, ContextApplication, execute_with_recovered_context,
)


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


_USER_AUTHORITY_KINDS = frozenset({
    "user_instruction", "user_fact", "user_correction", "user_preference",
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
        # A proposal is still only a candidate. The host's memory authority
        # policy must decide persistence; no internal ChatGPT memory is changed.


def _snapshot(envelope: ContinuationEnvelope) -> dict[str, Any]:
    return {
        "operation_key": envelope.operation_key,
        "chat_session_id": envelope.chat_session_id,
        "mission_id": envelope.mission_id,
        "source_ref": envelope.source_ref,
        "cursor": envelope.cursor,
        "corrections": list(envelope.corrections),
        "response_text": envelope.response_text,
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
    """Admit -> invoke -> validate -> reserve -> persist -> independent readback.

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
        output = invoke_model(receipt)
        _validate_output(output, receipt, resolve_source)
        key = ":".join((mission, "model", session, turn))
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
            reserved = reserve(key)
        except Exception as exc:
            raise GatewayDenied("durable reservation unavailable") from exc
        if reserved is not True:
            raise GatewayDenied("operation already reserved; reconcile before replay")
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
