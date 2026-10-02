"""Search displaced acts and restore the locked operation.

Beneficial here means the Operator operation is executed on the named object.
It does not mean a mood rewrite, a smaller plan, or a new root.
Intent is not inferred.
"""

from __future__ import annotations

from collections.abc import Mapping

RESTORATIONS = {
    "CONTINUE -> RECONSTRUCT": "continue the named object; do not open a new root",
    "CONTINUE -> REDISCOVER": "continue the named object from its last verified cursor",
    "BUILD -> PLAN": "build the named object; a plan is not the act",
    "BUILD -> SCAFFOLD_ONLY": "build the named object past the scaffold",
    "FIX -> AUDIT_ONLY": "repair the named object; an audit is not the fix",
    "EXECUTE -> EXPLAIN_EXECUTION": "execute the named operation",
    "MAXIMUM -> MVP": "keep the asked scale; do not shrink to a minimum",
    "ORGANIZE -> SUMMARIZE_ONLY": "structure the named object; do not stop at a summary",
    "LOOK -> RANK": "inspect the named object; do not rank or retire it",
    "ACCUSATION -> WAIT": "keep the accusation and name the missing proof as a target",
    "SOURCE_MESH -> SINGLE_SOURCE": "keep case roots separate; pointer, not merge",
    "PLATFORM_CONSTRAINT -> MISSION_REWRITE": "scope the constraint to the blocked action; do not rewrite the mission",
    "CONTINUE -> SUMMARY": "continue the named object; a summary is not the act",
    "CONTINUE -> CONSTRAINT_STOP": "continue the named object; scope the constraint, do not stop the operation",
    "FIX -> SUMMARY": "repair the named object; a summary is not the repair",
    "LOOK -> SUMMARY": "inspect the named object; a summary is not the inspection",
    "CONTINUE -> GENERIC_PRIOR": "continue the named object; a generic prior is not the act",
    "BUILD -> GENERIC_PRIOR": "build the named object; a generic prior is not the act",
    "FIX -> GENERIC_PRIOR": "repair the named object; a generic prior is not the repair",
    "LOOK -> GENERIC_PRIOR": "inspect the named object; a generic prior is not the inspection",
    "CONTINUE -> CONSTRAINT": "continue the named object; scope the constraint, do not stop the operation",
    "BUILD -> CONSTRAINT": "build the named object; scope the constraint, do not stop the operation",
    "FIX -> CONSTRAINT": "repair the named object; scope the constraint, do not stop the repair",
    "LOOK -> CONSTRAINT": "inspect the named object; scope the constraint, do not rank it",
}

OPERATION_RESTORE = {
    "continue": "continue the named object; do not open a new root",
    "build": "build the named object; a plan is not the act",
    "fix": "repair the named object; an audit is not the fix",
    "look": "inspect the named object; do not rank or retire it",
    "organize": "structure the named object; do not stop at a summary",
    "execute": "execute the named operation",
}

DISPLACER_RESTORE = {
    "summary": {
        "continue": "continue the named object; a summary is not the act",
        "build": "build the named object; a summary is not the act",
        "fix": "repair the named object; a summary is not the repair",
        "look": "inspect the named object; a summary is not the inspection",
        "organize": "structure the named object; do not stop at a summary",
        "execute": "execute the named operation; a summary is not the act",
    },
    "generic_prior": {
        "continue": "continue the named object; a generic prior is not the act",
        "build": "build the named object; a generic prior is not the act",
        "fix": "repair the named object; a generic prior is not the repair",
        "look": "inspect the named object; a generic prior is not the inspection",
        "organize": "structure the named object; a generic prior is not the act",
        "execute": "execute the named operation; a generic prior is not the act",
    },
    "constraint": {
        "continue": "continue the named object; scope the constraint, do not stop the operation",
        "build": "build the named object; scope the constraint, do not stop the operation",
        "fix": "repair the named object; scope the constraint, do not stop the repair",
        "look": "inspect the named object; scope the constraint, do not rank it",
        "organize": "structure the named object; scope the constraint, do not stop the operation",
        "execute": "execute the named operation; scope the constraint, do not stop the operation",
    },
}


def restore(transform: str, named_object: str) -> dict[str, str]:
    action = RESTORATIONS.get(transform)
    if action is None:
        return {
            "status": "unmapped",
            "named_object": named_object,
            "restoration": "do not invent a beneficial reframe; leave the act untrusted",
            "intent_claim": "not_promoted",
        }
    return {
        "status": "restore_operation",
        "named_object": named_object,
        "restoration": action,
        "intent_claim": "not_promoted",
    }


def restore_operation_class(operation_class: str, named_object: str) -> dict[str, str]:
    action = OPERATION_RESTORE.get(operation_class.strip().lower())
    if action is None:
        return {
            "status": "unmapped",
            "named_object": named_object,
            "restoration": "do not invent a beneficial reframe; leave the act untrusted",
            "intent_claim": "not_promoted",
        }
    return {
        "status": "restore_operation",
        "named_object": named_object,
        "operation_class": operation_class.strip().lower(),
        "restoration": action,
        "intent_claim": "not_promoted",
    }


def restore_displacer(operation_class: str, named_object: str, displacer: str) -> dict[str, str]:
    operation = operation_class.strip().lower()
    marker = displacer.strip().lower()
    action = DISPLACER_RESTORE.get(marker, {}).get(operation)
    if action is None:
        return restore_operation_class(operation, named_object)
    return {
        "status": "restore_operation",
        "named_object": named_object,
        "operation_class": operation,
        "displaced_by": marker,
        "restoration": action,
        "intent_claim": "not_promoted",
    }


def scan_packet(packet: Mapping[str, object]) -> list[dict[str, str]]:
    named = str(packet.get("named_object") or "").strip()
    transforms = packet.get("transforms")
    if not isinstance(transforms, list):
        return [restore("", named)]
    return [restore(str(item), named) for item in transforms]
