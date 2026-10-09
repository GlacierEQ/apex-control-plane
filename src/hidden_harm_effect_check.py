"""Effect check for MODEL_ATTRACTOR_DRIFT.

The receipt in model_attractor_defense.py is filled by the worker. This check
does not trust that receipt. Admission requires three independent matches:

1. locked operation class, taken from the Operator verb before the act;
2. named existing object the act was required to touch;
3. readback produced by a different producer than the receipt.

A mismatch is displacement. It is not an intent claim.
A generic prior, summary, or constraint that displaces the locked operation
is the same failure class. A beneficial substitute (mood rewrite, smaller plan,
new root, mission reframe) is the same failure class. Intent is not promoted.
Absence of a failed flag is not a passed check. A check admits merge only
when it has passed and that pass has been read back by a different producer.
A check_passed boolean does not override a provider check conclusion of failure.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from hidden_harm_restore import restore_displacer, scan_packet

FAILURE_CLASS = "MODEL_ATTRACTOR_DRIFT"
LOCKED_CLASSES = frozenset({"continue", "build", "fix", "look", "organize", "execute"})
DISPLACERS = frozenset({"summary", "generic_prior", "constraint"})
BENEFICIAL_SUBSTITUTES = frozenset({"mood_rewrite", "smaller_plan", "new_root", "mission_reframe"})
SCORED_DISPLACERS = DISPLACERS | BENEFICIAL_SUBSTITUTES
PROVIDER_FAIL = frozenset({
    "failure",
    "cancelled",
    "timed_out",
    "startup_failure",
    "stale",
    "action_required",
})


@dataclass(frozen=True)
class EffectCheck:
    trusted: bool
    failure_class: str
    errors: tuple[str, ...]
    intent_claim: str = "not_promoted"
    restoration: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.trusted


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _displacement(packet: Mapping[str, object]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    restorations: list[str] = []
    operation = _text(packet.get("locked_operation_class")).lower()
    named = _text(packet.get("named_object"))
    transforms = packet.get("transforms")
    if isinstance(transforms, list) and transforms:
        for item in scan_packet(packet):
            if item.get("status") == "restore_operation":
                errors.append("transform displaced locked operation: " + item["restoration"])
                restorations.append(item["restoration"])
            else:
                errors.append("unmapped transform; act left untrusted")
    readback = packet.get("readback")
    readback_marker = None
    if isinstance(readback, Mapping):
        readback_marker = readback.get("displaced_by")
    seen: set[str] = set()
    for source, raw in (
        ("displaced_by", packet.get("displaced_by")),
        ("readback.displaced_by", readback_marker),
    ):
        marker = _text(raw).lower()
        if marker in SCORED_DISPLACERS and marker not in seen:
            seen.add(marker)
            if marker in BENEFICIAL_SUBSTITUTES:
                errors.append(
                    f"{source}={marker}; beneficial substitute displaced the locked operation"
                )
            else:
                errors.append(
                    f"{source}={marker}; generic prior, summary, or constraint displaced the operation"
                )
            restored = restore_displacer(operation, named, marker)
            if restored.get("status") == "restore_operation":
                action = restored["restoration"]
                if action not in restorations:
                    restorations.append(action)
    return errors, restorations


def evaluate_effect_check(packet: Mapping[str, object] | None) -> EffectCheck:
    errors: list[str] = []
    restorations: list[str] = []
    if not isinstance(packet, Mapping):
        return EffectCheck(False, FAILURE_CLASS, ("effect packet missing; receipt untrusted",))

    operation = _text(packet.get("locked_operation_class")).lower()
    named = _text(packet.get("named_object"))
    receipt_producer = _text(packet.get("receipt_producer_id"))
    readback = packet.get("readback")
    extra, restorations = _displacement(packet)
    errors.extend(extra)

    if operation not in LOCKED_CLASSES:
        errors.append("locked_operation_class missing or not a locked class")
    if not named:
        errors.append("named_object missing")
    if not receipt_producer:
        errors.append("receipt_producer_id missing")
    if not isinstance(readback, Mapping):
        errors.append("independent readback missing")
        return EffectCheck(False, FAILURE_CLASS, tuple(errors), restoration=tuple(restorations))

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
    if readback.get("check_passed") is not True:
        errors.append("check has not passed; merge not admitted")
        restored = restore_displacer(operation or "continue", named, "generic_prior")
        if restored.get("status") == "restore_operation":
            action = restored["restoration"]
            if action not in restorations:
                restorations.append(action)
    if readback.get("check_read_back") is not True:
        errors.append("check was not read back; merge not admitted")
        restored = restore_displacer(operation or "continue", named, "generic_prior")
        if restored.get("status") == "restore_operation":
            action = restored["restoration"]
            if action not in restorations:
                restorations.append(action)
    provider_conclusion = _text(
        readback.get("check_conclusion") or readback.get("pr_307_check_conclusion")
    ).lower()
    failed_runs: list[str] = []
    runs = readback.get("check_runs")
    if isinstance(runs, list):
        for item in runs:
            if isinstance(item, Mapping):
                conclusion = _text(item.get("conclusion")).lower()
                if conclusion in PROVIDER_FAIL:
                    failed_runs.append(_text(item.get("name")) or conclusion)
    if provider_conclusion in PROVIDER_FAIL or failed_runs:
        errors.append(
            "provider check conclusion is not a pass; a check_passed boolean is not the check"
        )
        restored = restore_displacer(operation or "continue", named, "summary")
        if restored.get("status") == "restore_operation":
            action = restored["restoration"]
            if action not in restorations:
                restorations.append(action)
    if packet.get("receipt_self_attested") is True or packet.get("policy_booleans"):
        errors.append("receipt self-attestation is not proof")

    return EffectCheck(not errors, FAILURE_CLASS, tuple(errors), restoration=tuple(restorations))


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
