#!/usr/bin/env python3
"""Single-entry owner-local GLACIEREQ startup and independent context verification.

This is an executable entrypoint, NOT a native ChatGPT host startup hook.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate owner response member: ' + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('nonfinite owner response constant: ' + value)


def _run(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("owner command failed: " + result.stderr.strip()[:800])
    try:
        data = json.loads(result.stdout, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (ValueError, TypeError) as exc:
        raise ValueError("owner command returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("owner command must return an object")
    return data


def enter(*, owner_script, profile, session_id, invocation_id, output_dir, database,
          python_executable=sys.executable):
    base = [python_executable, str(owner_script)]
    common = ["--profile", str(profile), "--session-id", session_id,
              "--invocation-id", invocation_id]
    started = _run(base + ["mission-start"] + common + [
        "--output-dir", str(output_dir), "--database", str(database), "--auto-resume"])
    if started.get("status") != "REGISTERED_HANDLER_EFFECT_VERIFIED":
        raise ValueError("startup did not verify registered handler")
    packet = started.get("context_packet")
    if (not isinstance(packet, dict) or packet.get("next_transition") != "RESUME_FROM_VERIFIED_CURSOR"
            or packet.get("status") not in ("CONTEXT_PACKET_CREATED", "CONTEXT_PACKET_REPLAY_VERIFIED")
            or not isinstance(packet.get("path"), str) or not packet["path"]
            or not isinstance(packet.get("digest"), str) or not packet["digest"].startswith("sha256:")):
        raise ValueError("startup did not produce a verified, conflict-free context packet")
    consumed = _run(base + ["context-consume"] + common + [
        "--packet-path", packet["path"], "--packet-digest", packet["digest"]])
    if (consumed.get("status") != "CONTEXT_CONSUMED_PROVIDER_VERIFIED"
            or consumed.get("next_transition") != "RESUME_FROM_VERIFIED_CURSOR"
            or consumed.get("native_chatgpt_startup_verified") is not False
            or not isinstance(consumed.get("source_evidence"), list)
            or not consumed["source_evidence"]
            or not isinstance(consumed.get("recovered_cursor"), str)
            or not consumed["recovered_cursor"].strip()):
        raise ValueError("independent context consumer did not verify source-backed continuation")
    return {"status": "MISSION_CONTEXT_READY", "session_id": session_id,
            "invocation_id": invocation_id, "context": consumed,
            "packet_digest": packet["digest"], "native_chatgpt_startup_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("profile", "session-id", "invocation-id", "output-dir", "database"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--owner-script", type=Path,
                        default=Path(__file__).resolve().with_name("run_owned_continuity.py"))
    args = parser.parse_args()
    try:
        result = enter(owner_script=args.owner_script, profile=args.profile,
                       session_id=args.session_id, invocation_id=args.invocation_id,
                       output_dir=args.output_dir, database=args.database)
        print(json.dumps(result, sort_keys=True))
    except (ValueError, RuntimeError, OSError) as exc:
        print("FAIL_CLOSED: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
