#!/usr/bin/env python3
"""Owner-local GLACIEREQ continuity process: start with authenticated recovery.

Never a native ChatGPT startup hook. Executes only registered local cloud
indexing via Spiral -> APEX gateway, then SQLite checkpoint and readback.
"""
from __future__ import annotations

import argparse
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
    return profile


def run_profile(path: Path, *, session_id: str, invocation_id: str) -> dict:
    profile = load_profile(path)
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
    return {
        "status": "CHECKPOINT_VERIFIED", "checkpoint_key": key,
        "checkpoint_digest": saved.digest, "journal_source_ref": saved.source_ref,
        "cursor": saved.cursor, "corrections_applied": list(saved.corrections),
        "native_chatgpt_startup_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GLACIEREQ owned continuity host")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Recover, apply, execute local index, checkpoint")
    run.add_argument("--profile", type=Path, required=True)
    run.add_argument("--session-id", required=True)
    run.add_argument("--invocation-id", required=True)
    search = sub.add_parser("search", help="Read verified local cloud index")
    search.add_argument("--profile", type=Path, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    readback = sub.add_parser("readback", help="Verify existing committed mission receipt")
    readback.add_argument("--profile", type=Path, required=True)
    readback.add_argument("--session-id", required=True)
    readback.add_argument("--invocation-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run_profile(args.profile, session_id=args.session_id,
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
