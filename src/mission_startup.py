"""Controlled-host mission startup: authenticated Spiral recovery before APEX action.

The controlling host must call this entrypoint; no native ChatGPT hook is claimed.
"""
import json
import subprocess
import sys
from src.apex_session_gateway import Recovery, GatewayDenied, run_admitted_session


def recover_authenticated_mission(*, bridge, store, spiral_root, mission_id, session_id,
                                  required_fact_keys=(), runner=subprocess.run):
    if not isinstance(mission_id, str) or not mission_id.strip() or not isinstance(session_id, str) or not session_id.strip():
        raise GatewayDenied("explicit mission and session identity required")
    command = [sys.executable, str(bridge), "--store", str(store), "--spiral-root",
               str(spiral_root), "--mission-id", mission_id, "recover", "--session-id", session_id]
    try:
        result = runner(command, capture_output=True, text=True, check=True, timeout=30)
        # Reject duplicate JSON members that could override source bindings.
        def unique_members(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError('duplicate recovery JSON member')
                obj[key] = value
            return obj
        # Reject Python's nonstandard NaN/Infinity JSON extensions before context admission.
        def reject_nonfinite(value):
            raise ValueError("non-finite recovery JSON constant")
        payload = json.loads(result.stdout, object_pairs_hook=unique_members,
                             parse_constant=reject_nonfinite)
    except (subprocess.SubprocessError, OSError, ValueError, TypeError) as exc:
        raise GatewayDenied("authenticated recovery unavailable") from exc
    if not isinstance(payload, dict) or payload.get("status") != "VERIFIED_EXISTING" or payload.get("mission_id") != mission_id or payload.get("session_id") != session_id:
        raise GatewayDenied("recovery identity/status mismatch")
    if payload.get("requires_actual_action_application") is not True or payload.get("automatic_chatgpt_host_hook_verified") is not False:
        raise GatewayDenied("recovery capability contract mismatch")
    head = payload.get("head")
    if not isinstance(head, str) or len(head) != 64 or any(c not in "0123456789abcdef" for c in head) or payload.get("source_ref") != "spiral-journal:" + head:
        raise GatewayDenied("recovery source binding mismatch")
    corrections, facts, cursor = payload.get("corrections"), payload.get("facts"), payload.get("cursor")
    if not isinstance(corrections, list) or any(not isinstance(c, str) or not c.strip() for c in corrections) or not isinstance(facts, dict) or not isinstance(cursor, str):
        raise GatewayDenied("malformed recovered context")
    # Retain fact provenance in immutable serialized records, not unverified paraphrases.
    if any(not isinstance(k, str) or not isinstance(v, dict) or not isinstance(v.get("source"), str) or not v["source"].strip() for k, v in facts.items()):
        raise GatewayDenied("recovered fact provenance missing")
    # A resumed inspect cursor must never reach the model without its sourced fact.
    if cursor.startswith("inspect:") and (not cursor[8:] or cursor[8:] not in facts):
        raise GatewayDenied("inspection cursor has no recovered sourced fact")
    if isinstance(required_fact_keys, (str, bytes)) or not isinstance(required_fact_keys, (tuple, list)) or any(
        not isinstance(key, str) or not key.strip() for key in required_fact_keys
    ):
        raise GatewayDenied("required fact keys must be a sequence of nonempty strings")
    if not set(required_fact_keys).issubset(facts):
        raise GatewayDenied("required sourced facts missing from recovery")
    fact_records = tuple(json.dumps({"key": k, "record": facts[k]}, sort_keys=True) for k in sorted(facts))
    return Recovery(mission_id, payload["source_ref"], cursor, tuple(corrections),
                    fact_records, bool(cursor or corrections or facts))


def run_authenticated_mission(*, bridge, store, spiral_root, mission_id, session_id,
                              invocation_id, apply_context, invoke_model, resolve_source,
                              reserve, persist, readback, required_fact_keys=(), runner=subprocess.run):
    """Recover first, then require source-matched application and durable readback."""
    recovered = recover_authenticated_mission(
        bridge=bridge, store=store, spiral_root=spiral_root,
        mission_id=mission_id, session_id=session_id,
        required_fact_keys=required_fact_keys, runner=runner)
    return run_admitted_session(
        journal=recovered, chat_session_id=session_id, kernel=None,
        expected_mission_id=mission_id, invocation_id=invocation_id,
        apply_context=apply_context, invoke_model=invoke_model,
        resolve_source=resolve_source, reserve=reserve, persist=persist,
        readback=readback)
