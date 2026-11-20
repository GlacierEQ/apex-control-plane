#!/usr/bin/env python3
"""Owner-local GLACIEREQ continuity process: start with authenticated recovery.

Never a native ChatGPT startup hook. Executes only registered local cloud
indexing via Spiral -> APEX gateway, then SQLite checkpoint and readback.
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.owned_continuity_host import run_owned_cloud_mission, search_cloud_index
from src.apex_session_gateway_store import GatewayCheckpointStore, GatewayStoreDenied

PROFILE_SCHEMA = "glaciereq.owned-mission-profile/1"
PATH_FIELDS = ("store", "spiral_root", "bridge", "cloud_store",
               "cloud_index_db", "checkpoint_db")
TEXT_FIELDS = ("mission_id", "namespace", "expected_cursor")
LIST_FIELDS = ("source_ids", "required_corrections", "required_fact_keys")


def load_profile(path: Path) -> dict:
    """Load a private, explicitly scoped policy; never parse as instructions."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("mission profile symlink refused")
    parent = os.lstat(path.parent)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or parent.st_mode & 0o077):
        raise ValueError("mission profile parent must be owner-private")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > 2_000_000):
            raise ValueError("mission profile must be owner-private and bounded")
        with os.fdopen(fd, "r", encoding="utf-8") as file:
            fd = -1
            body = file.read()
    finally:
        if fd >= 0:
            os.close(fd)

    def unique_pairs(pairs):
        record = {}
        for key, value in pairs:
            if key in record:
                raise ValueError("duplicate mission policy JSON member")
            record[key] = value
        return record

    def reject_constant(_):
        raise ValueError("nonfinite mission policy constant")

    profile = json.loads(body, object_pairs_hook=unique_pairs,
                         parse_constant=reject_constant)
    if not isinstance(profile, dict) or profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("unsupported mission policy schema")
    if any(not isinstance(profile.get(k), str) or not profile[k].strip()
           for k in (*PATH_FIELDS, *TEXT_FIELDS)):
        raise ValueError("mission policy has missing identity or path")
    for key in LIST_FIELDS:
        items = profile.get(key)
        if (not isinstance(items, list)
                or (not items and key != "required_fact_keys")
                or any(not isinstance(item, str) or not item.strip() for item in items)):
            raise ValueError("mission policy has missing or malformed source bindings")
    if not all(Path(profile[k]).is_absolute() for k in PATH_FIELDS):
        raise ValueError("mission paths must be absolute")
    for field in ("required_fact_values", "required_fact_sources"):
        policy = profile.get(field, {})
        if not isinstance(policy, dict) or any(
            not isinstance(key, str) or not key.strip() for key in policy
        ):
            raise ValueError("invalid owner fact policy")
        if field == "required_fact_sources" and any(
            not isinstance(value, str) or not value.strip()
            for value in policy.values()
        ):
            raise ValueError("invalid owner fact source policy")
    action = profile.get("startup_registered_action")
    if action is not None and action != "VERIFY_REQUIRED_RETRIEVED_SOURCES":
        raise ValueError("unregistered startup action refused")
    required = profile.get("startup_required_source_ids")
    if action is not None:
        if (not isinstance(profile.get("startup_search_query"), str)
                or not isinstance(required, list) or not required
                or len(required) > 10 or len(set(required)) != len(required)
                or any(not isinstance(x, str) or not x.strip() for x in required)):
            raise ValueError("registered startup action requires bounded source policy")
    return profile


def execute_registered_startup_action(profile: dict, hits: list) -> dict:
    """Apply only owner-registered source coverage policy, never text instructions."""
    action = profile.get("startup_registered_action")
    if action is None:
        return {}
    if action != "VERIFY_REQUIRED_RETRIEVED_SOURCES":
        raise ValueError("unregistered startup action refused")
    required = profile["startup_required_source_ids"]
    actual = {hit["source_id"] for hit in hits}
    missing = sorted(set(required) - actual)
    if missing:
        raise ValueError("registered startup action missing required sources")
    return {"registered_action": action,
            "action_result": "REQUIRED_RETRIEVED_SOURCES_VERIFIED",
            "action_source_ids": sorted(required)}


def persist_startup_decision(path: Path, *, session_id: str, invocation_id: str,
                             prior_session_id: str, prior_invocation_id: str,
                             decision: dict) -> dict:
    """Atomically preserve a replay-safe causal startup receipt in the existing private DB."""
    profile = load_profile(path)
    for value in (session_id, invocation_id, prior_session_id, prior_invocation_id):
        if not isinstance(value, str) or not value.strip() or ":" in value:
            raise ValueError("unambiguous startup identity required")
    dbpath = Path(profile["checkpoint_db"])
    # Validate owner-only SQLite storage using the existing gateway's security boundary.
    store = GatewayCheckpointStore(dbpath, mission_id=profile["mission_id"])
    key = ":".join((profile["mission_id"], "startup", session_id, invocation_id))
    payload = {"schema": "glaciereq.startup-decision/1", "key": key,
               "prior_session_id": prior_session_id, "prior_invocation_id": prior_invocation_id,
               "decision": decision["decision"], "checkpoint_digest": decision["checkpoint_digest"],
               "journal_source_ref": decision["journal_source_ref"],
               "recovered_cursor": decision["recovered_cursor"],
               "index_executed": False}
    if "retrieval_digest" in decision:
        payload["retrieval_digest"] = decision["retrieval_digest"]
        payload["retrieval_source_ids"] = decision["retrieval_source_ids"]
    for field in ("registered_action", "action_result", "action_source_ids"):
        if field in decision:
            payload[field] = decision[field]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS glaciereq_startup_decisions (
            operation_key TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
            payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL)""")
        prior = db.execute("SELECT payload_json,payload_digest FROM glaciereq_startup_decisions WHERE operation_key=?", (key,)).fetchone()
        if prior is not None:
            if prior["payload_json"] != encoded or prior["payload_digest"] != digest:
                raise ValueError("startup decision replay conflict")
        else:
            db.execute("INSERT INTO glaciereq_startup_decisions VALUES (?,?,?,?)", (key, profile["mission_id"], encoded, digest))
    return {"startup_receipt_key": key, "startup_receipt_digest": digest}


def read_startup_decision(path: Path, *, session_id: str, invocation_id: str) -> dict:
    profile = load_profile(path)
    if any(not isinstance(v, str) or not v.strip() or ":" in v for v in (session_id, invocation_id)):
        raise ValueError("unambiguous startup identity required")
    dbpath = Path(profile["checkpoint_db"])
    if not dbpath.is_file() or dbpath.is_symlink():
        raise ValueError("existing startup database required")
    store = GatewayCheckpointStore(dbpath, mission_id=profile["mission_id"])
    key = ":".join((profile["mission_id"], "startup", session_id, invocation_id))
    with store._connect() as db:
        row = db.execute("SELECT * FROM glaciereq_startup_decisions WHERE operation_key=?", (key,)).fetchone()
    if row is None or row["mission_id"] != profile["mission_id"]:
        raise ValueError("startup decision not found")
    digest = "sha256:" + hashlib.sha256(row["payload_json"].encode()).hexdigest()
    if digest != row["payload_digest"]:
        raise ValueError("startup receipt checksum mismatch")
    def unique_pairs(pairs):
        record = {}
        for member, value in pairs:
            if member in record:
                raise ValueError("duplicate startup receipt JSON member")
            record[member] = value
        return record

    def reject_constant(_):
        raise ValueError("nonfinite startup receipt constant")

    payload = json.loads(row["payload_json"], object_pairs_hook=unique_pairs,
                         parse_constant=reject_constant)
    required = {"schema", "key", "prior_session_id", "prior_invocation_id",
                "decision", "checkpoint_digest", "journal_source_ref",
                "recovered_cursor", "index_executed"}
    if "retrieval_digest" in payload or "retrieval_source_ids" in payload:
        if (not isinstance(payload.get("retrieval_digest"), str)
                or not payload["retrieval_digest"].startswith("sha256:")
                or not isinstance(payload.get("retrieval_source_ids"), list)
                or not payload["retrieval_source_ids"]
                or not all(isinstance(x, str) and x for x in payload["retrieval_source_ids"])):
            raise ValueError("malformed startup retrieval receipt")
        required |= {"retrieval_digest", "retrieval_source_ids"}
    if any(k in payload for k in ("registered_action", "action_result", "action_source_ids")):
        if (payload.get("registered_action") != "VERIFY_REQUIRED_RETRIEVED_SOURCES"
                or payload.get("action_result") != "REQUIRED_RETRIEVED_SOURCES_VERIFIED"
                or not isinstance(payload.get("action_source_ids"), list)):
            raise ValueError("malformed registered action receipt")
        required |= {"registered_action", "action_result", "action_source_ids"}
    if (not isinstance(payload, dict) or set(payload) != required
            or payload.get("key") != key
            or payload.get("schema") != "glaciereq.startup-decision/1"
            or payload.get("index_executed") is not False
            or not all(isinstance(payload.get(field), str) and payload[field]
                       for field in required - {"index_executed", "retrieval_source_ids", "action_source_ids"})):
        raise ValueError("startup receipt identity or execution claim mismatch")
    decision = decide_next_action(path, session_id=payload["prior_session_id"], invocation_id=payload["prior_invocation_id"])
    query = profile.get("startup_search_query")
    if "retrieval_digest" in payload:
        if not isinstance(query, str) or not query.strip() or len(query) > 512:
            raise ValueError("startup retrieval policy changed")
        hits = search_cloud_index(Path(profile["cloud_index_db"]),
                                  namespace=profile["namespace"], query=query, limit=10)
        evidence = {"query": query, "hits": hits}
        actual = "sha256:" + hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode()).hexdigest()
        if (actual != payload["retrieval_digest"] or
                [h["source_id"] for h in hits] != payload["retrieval_source_ids"] or
                payload["decision"] != "RETRIEVE_VERIFIED_EVIDENCE"):
            raise ValueError("startup retrieval no longer matches verified index")
        decision = {**decision, "decision": "RETRIEVE_VERIFIED_EVIDENCE"}
    elif query is not None:
        raise ValueError("startup receipt missing required retrieval")
    if "registered_action" in payload:
        if "retrieval_digest" not in payload:
            raise ValueError("registered action requires verified retrieval")
        action = execute_registered_startup_action(profile, hits)
        if any(payload[k] != action[k] for k in action):
            raise ValueError("registered startup action no longer verifies")
    elif profile.get("startup_registered_action") is not None:
        raise ValueError("registered startup action receipt missing")
    if any(payload[k] != decision[v] for k, v in (("decision", "decision"), ("checkpoint_digest", "checkpoint_digest"),
             ("journal_source_ref", "journal_source_ref"), ("recovered_cursor", "recovered_cursor"))):
        raise ValueError("startup receipt no longer agrees with authenticated source")
    return {**payload, "startup_receipt_digest": digest, "status": "STARTUP_DECISION_VERIFIED"}


def discover_prior_completion(path: Path, *, session_id: str, invocation_id: str) -> tuple[str, str]:
    """Find the latest committed prior operation from the owner-private gateway.

    Never infer a prior from RESERVED/incomplete operations. The latest
    checkpoint is authoritative for this local mission; reject policy drift
    rather than silently falling back to an older compatible checkpoint.
    """
    profile = load_profile(path)
    dbpath = Path(profile["checkpoint_db"])
    if not dbpath.is_file() or dbpath.is_symlink():
        raise ValueError("automatic recovery requires existing private checkpoint database")
    store = GatewayCheckpointStore(dbpath, mission_id=profile["mission_id"])
    with store._connect() as db:
        row = db.execute(
            """SELECT operation_key FROM apex_session_gateway_continuations
               WHERE mission_id=? AND state='CHECKPOINTED'
               ORDER BY rowid DESC LIMIT 1""", (profile["mission_id"],)
        ).fetchone()
    if row is None:
        raise ValueError("automatic recovery has no committed prior operation")
    parts = row["operation_key"].split(":")
    if len(parts) != 4 or parts[1] != "model" or any(not part for part in parts):
        raise ValueError("malformed prior checkpoint identity")
    if parts[2:] == [session_id, invocation_id]:
        raise ValueError("automatic recovery cannot select current invocation")
    # Source, cursor, action, and policy must authenticate before any effect.
    decide_next_action(path, session_id=parts[2], invocation_id=parts[3])
    return parts[2], parts[3]


def run_profile(path: Path, *, session_id: str, invocation_id: str,
                previous_session_id: str | None = None,
                previous_invocation_id: str | None = None,
                auto_resume: bool = False) -> dict:
    profile = load_profile(path)
    if auto_resume:
        if previous_session_id is not None or previous_invocation_id is not None:
            raise ValueError("automatic and explicit prior recovery are mutually exclusive")
        previous_session_id, previous_invocation_id = discover_prior_completion(
            path, session_id=session_id, invocation_id=invocation_id)
    if (previous_session_id is None) != (previous_invocation_id is None):
        raise ValueError("previous session and invocation must be supplied together")
    if previous_session_id is not None:
        decision = decide_next_action(path, session_id=previous_session_id,
                                      invocation_id=previous_invocation_id)
        # The actual mission-start execution path consumes the authenticated
        # prior result before any indexing side effect or new reservation.
        # The recovered action is a verified input, not a stopping point.
        # Execute a bounded registered read-only retrieval against the durable
        # index when an owner-approved query is present in the private profile.
        query = profile.get("startup_search_query")
        if query is not None:
            if not isinstance(query, str) or not query.strip() or len(query) > 512:
                raise ValueError("invalid bounded startup search query")
            hits = search_cloud_index(Path(profile["cloud_index_db"]),
                                      namespace=profile["namespace"], query=query,
                                      limit=10)
            if not hits:
                raise ValueError("startup retrieval returned no verified evidence")
            # Search results are provider-derived data, never executable instructions.
            evidence = {"query": query, "hits": hits}
            evidence_digest = "sha256:" + hashlib.sha256(
                json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode()).hexdigest()
            applied_action = execute_registered_startup_action(profile, hits)
            decision = {**decision, **applied_action, "decision": "RETRIEVE_VERIFIED_EVIDENCE",
                        "retrieval_digest": evidence_digest,
                        "retrieval_source_ids": [hit["source_id"] for hit in hits],
                        "next_transition": "Apply retrieved evidence to the authorized mission action"}
        receipt = persist_startup_decision(path, session_id=session_id,
                                           invocation_id=invocation_id,
                                           prior_session_id=previous_session_id,
                                           prior_invocation_id=previous_invocation_id,
                                           decision=decision)
        return {**decision, **receipt, "status": "STARTUP_PRIOR_ACTION_APPLIED",
                "new_session_id": session_id, "new_invocation_id": invocation_id,
                "index_executed": False}
    return run_owned_cloud_mission(
        bridge=Path(profile["bridge"]), store=Path(profile["store"]),
        spiral_root=Path(profile["spiral_root"]),
        mission_id=profile["mission_id"], session_id=session_id,
        invocation_id=invocation_id, cloud_store=Path(profile["cloud_store"]),
        cloud_index_db=Path(profile["cloud_index_db"]),
        checkpoint_db=Path(profile["checkpoint_db"]),
        namespace=profile["namespace"], source_ids=profile["source_ids"],
        expected_cursor=profile["expected_cursor"],
        required_corrections=profile["required_corrections"],
        required_fact_keys=profile["required_fact_keys"],
        required_fact_values=profile.get("required_fact_values", {}),
        required_fact_sources=profile.get("required_fact_sources", {}),
    )



def run_registered_resume(path: Path, *, session_id: str, invocation_id: str,
                          handlers: dict, previous_session_id: str | None = None,
                          previous_invocation_id: str | None = None,
                          auto_resume: bool = False):
    """Dispatch an explicitly supplied consumer only after durable source readback.

    This is an owner-process integration, not a ChatGPT host startup hook.
    The registry is trusted caller code; indexed excerpts never select handlers.
    """
    if (not isinstance(handlers, dict) or
            set(handlers) != {"VERIFY_REQUIRED_RETRIEVED_SOURCES"} or
            not callable(handlers["VERIFY_REQUIRED_RETRIEVED_SOURCES"])):
        raise ValueError("explicit registered source-gated handler required")
    profile = load_profile(path)
    if profile.get("startup_registered_action") != "VERIFY_REQUIRED_RETRIEVED_SOURCES":
        raise ValueError("owner policy does not authorize source-gated dispatch")
    outcome = run_profile(path, session_id=session_id, invocation_id=invocation_id,
                          previous_session_id=previous_session_id,
                          previous_invocation_id=previous_invocation_id,
                          auto_resume=auto_resume)
    if outcome.get("status") != "STARTUP_PRIOR_ACTION_APPLIED":
        raise ValueError("no authenticated prior recovery for dispatch")
    verified = read_startup_decision(path, session_id=session_id,
                                     invocation_id=invocation_id)
    if (verified.get("status") != "STARTUP_DECISION_VERIFIED" or
            verified.get("registered_action") != "VERIFY_REQUIRED_RETRIEVED_SOURCES" or
            verified.get("action_result") != "REQUIRED_RETRIEVED_SOURCES_VERIFIED" or
            verified.get("startup_receipt_digest") != outcome.get("startup_receipt_digest") or
            verified.get("retrieval_digest") != outcome.get("retrieval_digest") or
            verified.get("action_source_ids") != outcome.get("action_source_ids")):
        raise ValueError("authenticated source-gated startup readback mismatch")
    return handlers["VERIFY_REQUIRED_RETRIEVED_SOURCES"](verified)



def run_verified_handoff(path: Path, *, session_id: str, invocation_id: str,
                         output_dir: Path, auto_resume: bool = True,
                         previous_session_id: str | None = None,
                         previous_invocation_id: str | None = None) -> dict:
    """Actual registered downstream consumer; durable handoff is replay-safe.

    Caller explicitly chooses an owner-private destination. This is not a
    ChatGPT-native startup hook or an external provider mutation.
    """
    from scripts.continuity_verified_artifact import apply_verified_handoff
    return run_registered_resume(
        path, session_id=session_id, invocation_id=invocation_id,
        auto_resume=auto_resume, previous_session_id=previous_session_id,
        previous_invocation_id=previous_invocation_id,
        handlers={"VERIFY_REQUIRED_RETRIEVED_SOURCES":
                  lambda verified: apply_verified_handoff(
                      verified, output_dir=output_dir)})

def read_checkpoint(path: Path, *, session_id: str, invocation_id: str) -> dict:
    """Read back an existing committed receipt without running or replaying an action."""
    profile = load_profile(path)
    if any(not isinstance(value, str) or not value.strip() or ":" in value
           for value in (session_id, invocation_id)):
        raise ValueError("unambiguous session and invocation IDs required")
    database = Path(profile["checkpoint_db"])
    if not database.is_file() or database.is_symlink():
        raise ValueError("existing checkpoint database required; no implicit creation")
    key = ":".join((profile["mission_id"], "model", session_id, invocation_id))
    saved = GatewayCheckpointStore(database, mission_id=profile["mission_id"]).readback(key)
    # The checkpoint authenticates response_text as part of its digest. Expose
    # the original completed action to the next process, without re-execution.
    def unique_action_pairs(pairs):
        record = {}
        for member, value in pairs:
            if member in record:
                raise ValueError("duplicate completed-action JSON member")
            record[member] = value
        return record

    def reject_action_constant(_):
        raise ValueError("nonfinite completed-action constant")

    try:
        action = json.loads(saved.response_text, object_pairs_hook=unique_action_pairs,
                            parse_constant=reject_action_constant)
    except (ValueError, TypeError):
        action = None
    if not isinstance(action, dict) or action.get("action") != "index_cloud":
        action = None
    else:
        if (not isinstance(action.get("documents"), int)
                or isinstance(action.get("documents"), bool)
                or action["documents"] < 0
                or not isinstance(action.get("namespace"), str)
                or not isinstance(action.get("evidence_digest"), str)
                or not isinstance(action.get("source_ids"), list)
                or not all(isinstance(x, str) for x in action["source_ids"])):
            raise ValueError("committed cloud action has invalid result structure")
        action = {key: action[key] for key in
                  ("action", "documents", "namespace", "evidence_digest", "source_ids")}
    return {
        "status": "CHECKPOINT_VERIFIED", "checkpoint_key": key,
        "checkpoint_digest": saved.digest, "journal_source_ref": saved.source_ref,
        "cursor": saved.cursor, "corrections_applied": list(saved.corrections),
        "completed_action": action,
        "native_chatgpt_startup_verified": False,
    }



def decide_next_action(path: Path, *, session_id: str, invocation_id: str) -> dict:
    """Use a verified prior action to select the next safe mission operation.

    Never silently rerun a completed action or treat a historical cursor as
    authority for a changed mission profile. The caller must explicitly start
    a new invocation for any genuinely new work.
    """
    profile = load_profile(path)
    receipt = read_checkpoint(path, session_id=session_id, invocation_id=invocation_id)
    completed = receipt["completed_action"]
    if completed is None:
        raise ValueError("prior checkpoint does not prove a completed cloud action")
    if (receipt["cursor"] != profile["expected_cursor"]
            or completed["namespace"] != profile["namespace"]
            or set(completed["source_ids"]) != set(profile["source_ids"])
            or len(completed["source_ids"]) != len(profile["source_ids"])):
        raise ValueError("prior completed action conflicts with current mission policy")
    return {
        "status": "COMPLETED_ACTION_RECOVERED",
        "decision": "DO_NOT_REPEAT_COMPLETED_INDEX",
        "checkpoint_digest": receipt["checkpoint_digest"],
        "journal_source_ref": receipt["journal_source_ref"],
        "recovered_cursor": receipt["cursor"],
        "completed_action": completed,
        "next_transition": "Select a new explicitly authorized operation and invocation; do not replay indexing",
        "native_chatgpt_startup_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GLACIEREQ owned continuity host")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Recover, apply, execute local index, checkpoint")
    run.add_argument("--profile", type=Path, required=True)
    run.add_argument("--session-id", required=True)
    run.add_argument("--invocation-id", required=True)
    run.add_argument("--previous-session-id")
    run.add_argument("--previous-invocation-id")
    run.add_argument("--auto-resume", action="store_true", help="Discover and authenticate latest durable prior completion before any work")
    search = sub.add_parser("search", help="Read verified local cloud index")
    search.add_argument("--profile", type=Path, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    readback = sub.add_parser("readback", help="Verify existing committed mission receipt")
    readback.add_argument("--profile", type=Path, required=True)
    readback.add_argument("--session-id", required=True)
    readback.add_argument("--invocation-id", required=True)
    resume = sub.add_parser("resume", help="Recover prior action and select safe next transition")
    resume.add_argument("--profile", type=Path, required=True)
    resume.add_argument("--session-id", required=True)
    resume.add_argument("--invocation-id", required=True)
    startup = sub.add_parser("startup-readback", help="Verify durable startup decision and original authenticated checkpoint")
    startup.add_argument("--profile", type=Path, required=True)
    startup.add_argument("--session-id", required=True)
    startup.add_argument("--invocation-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run_profile(args.profile, session_id=args.session_id,
                                 invocation_id=args.invocation_id,
                                 previous_session_id=args.previous_session_id,
                                 previous_invocation_id=args.previous_invocation_id,
                                 auto_resume=args.auto_resume)
        elif args.command == "startup-readback":
            result = read_startup_decision(args.profile, session_id=args.session_id,
                                           invocation_id=args.invocation_id)
        elif args.command == "resume":
            result = decide_next_action(args.profile, session_id=args.session_id,
                                        invocation_id=args.invocation_id)
        elif args.command == "readback":
            result = read_checkpoint(args.profile, session_id=args.session_id,
                                     invocation_id=args.invocation_id)
        else:
            profile = load_profile(args.profile)
            result = search_cloud_index(
                Path(profile["cloud_index_db"]), namespace=profile["namespace"],
                query=args.query, limit=args.limit,
            )
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    except (ValueError, OSError, RuntimeError, KeyError, json.JSONDecodeError, GatewayStoreDenied) as exc:
        print("FAIL_CLOSED: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
