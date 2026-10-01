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


def scan_packet(packet: Mapping[str, object]) -> list[dict[str, str]]:
    named = str(packet.get("named_object") or "").strip()
    transforms = packet.get("transforms")
    if not isinstance(transforms, list):
        return [restore("", named)]
    return [restore(str(item), named) for item in transforms]
