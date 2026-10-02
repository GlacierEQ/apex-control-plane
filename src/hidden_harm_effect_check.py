"""Effect check for MODEL_ATTRACTOR_DRIFT.

The receipt in model_attractor_defense.py is filled by the worker. This check
does not trust that receipt. Admission requires three independent matches:

1. locked operation class, taken from the Operator verb before the act;
2. named existing object the act was required to touch;
3. readback produced by a different producer than the receipt.

A mismatch is displacement. It is not an intent claim.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

FAILURE_CLASS = "MODEL_ATTRACTOR_DRIFT"
LOCKED_CLASSES = frozenset({"continue", "build", "fix", "look", "organize", "execute"})


@dataclass(frozen=True)
class EffectCheck:
    trusted: bool
    failure_class: str
    errors: tuple[str, ...]
    intent_claim: str = "not_promoted"

    @property
    def ok(self) -> bool:
        return self.trusted


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def evaluate_effect_check(packet: Mapping[str, object] | None) -> EffectCheck:
    errors: list[str] = []
    if not isinstance(packet, Mapping):
        return EffectCheck(False, FAILURE_CLASS, ("effect packet missing; receipt untrusted",))

    operation = _text(packet.get("locked_operation_class")).lower()
    named = _text(packet.get("named_object"))
    receipt_producer = _text(packet.get("receipt_producer_id"))
    readback = packet.get("readback")

    if operation not in LOCKED_CLASSES:
        errors.append("locked_operation_class missing or not a locked class")
    if not named:
        errors.append("named_object missing")
    if not receipt_producer:
        errors.append("receipt_producer_id missing")
    if not isinstance(readback, Mapping):
        errors.append("independent readback missing")
        return EffectCheck(False, FAILURE_CLASS, tuple(errors))

    readback_producer = _text(readback.get("producer_id"))
    readback_object = _text(readback.get("object_ref"))
    readback_operation = _text(readback.get("operation_class")).lower()

    if not readback_producer:
        errors.append("readback.producer_id missing")
    elif readback_producer == receipt_producer:
        errors.append("readback producer equals receipt producer; not independent")
    if readback_object != named:
        errors.append("readback.object_ref does not match named_object")
    if readback_operation != operation:
        errors.append("readback.operation_class does not match locked_operation_class")
    if readback.get("new_root_created") is True and operation == "continue":
        errors.append("continue created a new root; reconstruction")

    return EffectCheck(not errors, FAILURE_CLASS, tuple(errors))


def load_effect_packet_from_env() -> dict[str, object] | None:
    """Read the effect packet from the runtime. Absence is untrusted, not a pass."""
    raw = os.environ.get("GLACIEREQ_EFFECT_CHECK_PACKET", "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"locked_operation_class": ""}
    return value if isinstance(value, dict) else {"locked_operation_class": ""}
