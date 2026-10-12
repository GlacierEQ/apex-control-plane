#!/usr/bin/env python3
"""GlacierEQ's thin CLI adapter to the EXISTING authenticated Spiral/APEX recovery.

Explicit mission IDs only. A fresh chat is never allowed to recreate missing state.
This is an invocation surface, NOT an automatic ChatGPT host hook.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.spiral_live_journal import load_spiral_engine, open_authenticated_chat
from src.spiral_chat_handoff import recover_existing_chat_session

def fail(reason):
    raise ValueError(reason)

def secure_dir(path):
    if path.is_symlink():
        fail("symlink directories refused")
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
    if not path.is_dir():
        fail("expected private directory")
    # Do not change existing permissions silently; refuse access via broad modes.
    if path.stat().st_mode & 0o077:
        fail("directory permits group or other access: " + str(path))

def exclusive_bytes(path, data):
    if path.exists() or path.is_symlink():
        fail("existing path must not be recreated or overwritten")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())

def read_bytes(path):
    if path.is_symlink() or not path.is_file() or (path.stat().st_mode & 0o077):
        fail("required protected file missing, symlinked or insecure: " + str(path))
    return path.read_bytes()

def json_bytes(data):
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()

def replace_anchor(path, content):
    # Preserve independent head; only a successfully authenticated append advances it.
    if path.is_symlink():
        fail("anchor symlink refused")
    fd, name = tempfile.mkstemp(prefix=".anchor-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as h:
            h.write(json_bytes(content))
            h.flush()
            os.fsync(h.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def locations(base, mission):
    slug = hashlib.sha256(mission.encode()).hexdigest()[:32]
    folders = {k: base / k for k in ("journals", "keys", "anchors", "manifests")}
    return folders, {
        "journal": folders["journals"] / (slug + ".jsonl"),
        "key": folders["keys"] / (slug + ".key"),
        "anchor": folders["anchors"] / (slug + ".json"),
        "lock": folders["anchors"] / (slug + ".lock"),
        "manifest": folders["manifests"] / (slug + ".json"),
    }

def paths_existing(paths):
    return all(p.is_file() and not p.is_symlink() for p in paths.values())

def main():
    parser = argparse.ArgumentParser(description="Authenticated existing-mission Spiral context bridge")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--spiral-root", type=Path, required=True)
    parser.add_argument("--mission-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("init")
    create.add_argument("--objective", required=True)
    create.add_argument("--outcome", required=True)
    read = sub.add_parser("recover")
    read.add_argument("--session-id", required=True)
    for action in ("correct", "checkpoint", "fact"):
        s = sub.add_parser(action)
        if action == "correct":
            s.add_argument("--instruction", required=True)
        elif action == "checkpoint":
            s.add_argument("--cursor", required=True)
        else:
            s.add_argument("--key", required=True)
            s.add_argument("--value", required=True)
            s.add_argument("--source", required=True)
    args = parser.parse_args()
    if not args.mission_id.strip():
        fail("nonempty explicit mission ID required")
    base = args.store.expanduser()
    folders, paths = locations(base, args.mission_id)
    # Init intentionally creates one NEW mission. Recover and mutate MUST NOT create anything.
    if args.command == "init":
        secure_dir(base)
        for folder in folders.values():
            secure_dir(folder)
        if any(p.exists() or p.is_symlink() for p in paths.values()):
            fail("mission state already exists or is incomplete; manual reconciliation required")
        upstream = load_spiral_engine(args.spiral_root)
        integrity_key = os.urandom(32)
        exclusive_bytes(paths["key"], integrity_key)
        journal = upstream.ContinuityJournal(paths["journal"], args.mission_id,
                   args.objective, terminal_outcome=args.outcome, integrity_key=integrity_key)
        os.chmod(paths["journal"], 0o600)
        head = journal.events[-1]["sha256"]
        exclusive_bytes(paths["manifest"], json_bytes({
            "mission_id": args.mission_id, "objective": args.objective, "terminal_outcome": args.outcome,
            "schema": "glaciereq.context-spi-bridge.v1"
        }))
        exclusive_bytes(paths["anchor"], json_bytes({"mission_id": args.mission_id, "head": head}))
        exclusive_bytes(paths["lock"], b"")
        print(json.dumps({"status":"CREATED", "mission_id":args.mission_id, "head":head}))
        return
    if not base.is_dir() or base.is_symlink() or not paths_existing(paths):
        fail("required pre-existing mission journal, secret and anchor absent")
    for folder in folders.values():
        if folder.is_symlink() or folder.stat().st_mode & 0o077:
            fail("insecure continuity directory")
    # A stable dedicated lock serializes journal+head across independent ChatGPT processes.
    # The descriptor remains open (and the lock held) until this CLI process exits.
    lock_fd = os.open(paths["lock"], os.O_RDONLY | os.O_NOFOLLOW)
    if os.fstat(lock_fd).st_mode & 0o077:
        fail("insecure continuity lock")
    fcntl.flock(lock_fd, fcntl.LOCK_SH if args.command == "recover" else fcntl.LOCK_EX)
    manifest = json.loads(read_bytes(paths["manifest"]))
    anchor = json.loads(read_bytes(paths["anchor"]))
    secret = read_bytes(paths["key"])
    if manifest.get("mission_id") != args.mission_id or anchor.get("mission_id") != args.mission_id:
        fail("mission identity mismatch")
    journal, recovery = open_authenticated_chat(
        paths["journal"], spiral_source_root=args.spiral_root, 
        chat_session_id=(args.session_id if args.command == "recover" else "bridge-update"),
        mission_id=args.mission_id, objective=manifest["objective"],
        terminal_outcome=manifest["terminal_outcome"],
        integrity_key=secret, expected_head=anchor["head"]
    )
    if args.command == "recover":
        verified_fact_keys = tuple(dict.fromkeys(
            event["data"]["key"] for event in journal.events
            if event["kind"] in ("verified_fact", "superseded_fact")
        ))
        recovery = recover_existing_chat_session(journal, args.session_id,
                                                  fact_keys=verified_fact_keys)
        print(json.dumps({
            "status": "VERIFIED_EXISTING", "mission_id":recovery.mission_id,
            "objective":recovery.objective, "terminal_outcome":recovery.terminal_outcome,
            "session_id":recovery.chat_session_id, "head":anchor["head"],
            "source_ref":recovery.source_ref, "cursor":recovery.cursor,
            "corrections":recovery.corrections, "facts":recovery.facts,
            "requires_actual_action_application":True,
            "automatic_chatgpt_host_hook_verified":False
        }, indent=2))
        return
    if args.command == "correct":
        journal.correct(args.instruction)
    elif args.command == "checkpoint":
        journal.checkpoint(args.cursor)
    elif args.command == "fact":
        journal.verify_fact(args.key, args.value, source=args.source)
    new_head = journal.events[-1]["sha256"]
    replace_anchor(paths["anchor"], {"mission_id": args.mission_id, "head": new_head})
    # Independent readback from original adapter is mandatory.
    _, proof = open_authenticated_chat(
        paths["journal"], spiral_source_root=args.spiral_root, chat_session_id="bridge-write-readback",
        mission_id=args.mission_id, objective=manifest["objective"],
        terminal_outcome=manifest["terminal_outcome"], integrity_key=secret, expected_head=new_head)
    print(json.dumps({"status":"VERIFIED_UPDATE", "mission_id":proof.mission_id,
                      "head":new_head, "cursor":proof.cursor, "corrections_count":len(proof.corrections)}))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("FAIL_CLOSED: " + str(exc), file=sys.stderr)
        sys.exit(1)
