#!/usr/bin/env python3
"""GlacierEQ's thin CLI adapter to the EXISTING authenticated Spiral/APEX recovery.

Explicit mission IDs only. A fresh chat is never allowed to recreate missing state.
This is an invocation surface, NOT an automatic ChatGPT host hook.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from src.apex_runtime_kernel import create_verified_runtime_kernel
from src.spiral_live_journal import (
    load_spiral_engine,
    open_authenticated_chat,
    resume_authenticated_chat_in_apex,
)
from src.spiral_chat_handoff import recover_existing_chat_session
from src.continuity_action_gate import execute_recovered_action

def fail(reason):
    raise ValueError(reason)

def secure_dir(path, *, create=False):
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    # File-descriptor inspection avoids path-check / symlink races.
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            fail("expected owner-private directory: " + str(path))
    finally:
        os.close(fd)

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
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            fail("required owner-private regular file: " + str(path))
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd >= 0:
            os.close(fd)

@contextmanager
def mission_lock(path, *, read_only):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            fail("insecure continuity lock")
        fcntl.flock(fd, fcntl.LOCK_SH if read_only else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)

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
        # Persist the directory entry as well as the file bytes. Without this,
        # a power loss after a successful rename can lose the independent head.
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def sync_directory(path):
    """Persist newly created mission entries before reporting initialization."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

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

def main():
    parser = argparse.ArgumentParser(description="Authenticated existing-mission Spiral context bridge")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--spiral-root", type=Path, required=True)
    parser.add_argument("--mission-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("init")
    create.add_argument("--objective", required=True)
    create.add_argument("--outcome", required=True)
    sub.add_parser("reconcile", help="Repair interrupted anchor update only for an HMAC-validated journal descendant")
    read = sub.add_parser("recover")
    read.add_argument("--session-id", required=True)
    admit = sub.add_parser("admit", help="Recover authenticated journal and admit context into a real APEX runtime kernel")
    admit.add_argument("--session-id", required=True)
    dispatch = sub.add_parser("dispatch", help="Authenticated recovery followed by a registered downstream read-only action")
    dispatch.add_argument("--session-id", required=True)
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
        secure_dir(base, create=True)
        for folder in folders.values():
            secure_dir(folder, create=True)
        if any(p.exists() or p.is_symlink() for p in paths.values()):
            fail("mission state already exists or is incomplete; manual reconciliation required")
        upstream = load_spiral_engine(args.spiral_root)
        integrity_key = os.urandom(32)
        exclusive_bytes(paths["key"], integrity_key)
        journal = upstream.ContinuityJournal(paths["journal"], args.mission_id,
                   args.objective, terminal_outcome=args.outcome, integrity_key=integrity_key)
        os.chmod(paths["journal"], 0o600)
        events = journal.events
        if not events:
            fail("journal initialization did not persist a mission event")
        head = events[-1]["sha256"]
        exclusive_bytes(paths["manifest"], json_bytes({
            "mission_id": args.mission_id, "objective": args.objective, "terminal_outcome": args.outcome,
            "schema": "glaciereq.context-spi-bridge.v1"
        }))
        exclusive_bytes(paths["anchor"], json_bytes({"mission_id": args.mission_id, "head": head}))
        exclusive_bytes(paths["lock"], b"")
        # Persist every newly created mission entry and its parent directory.
        # An acknowledged init must not lose its key, journal, manifest or head
        # merely because their directory entries were not synced.
        for folder in folders.values():
            sync_directory(folder)
        sync_directory(base)
        print(json.dumps({"status":"CREATED", "mission_id":args.mission_id, "head":head}))
        return
    secure_dir(base)
    for folder in folders.values():
        secure_dir(folder)
    # Stable owner-only file lock covers authenticated read, append, and head update.
    with mission_lock(paths["lock"], read_only=(args.command in ("recover", "admit", "dispatch"))):
        manifest = json.loads(read_bytes(paths["manifest"]))
        anchor = json.loads(read_bytes(paths["anchor"]))
        secret = read_bytes(paths["key"])
        if manifest.get("mission_id") != args.mission_id or anchor.get("mission_id") != args.mission_id:
            fail("mission identity mismatch")
        if args.command == "reconcile":
            # A process can fsync an authenticated append, then exit before the
            # separate anchor rename. Recover that exact interrupted forward
            # transition, never a rollback, fork, fabricated mission or unauthenticated
            # journal. The prior anchored head remains the trust root.
            previous_head = anchor.get("head")
            if (not isinstance(previous_head, str) or len(previous_head) != 64
                    or any(ch not in "0123456789abcdef" for ch in previous_head)):
                fail("independently anchored revision is invalid")
            # Candidate head is untrusted until validated by the ORIGINAL
            # upstream Spiral HMAC chain and its protected journal reader.
            raw = read_bytes(paths["journal"])
            lines = raw.splitlines()
            if not lines:
                fail("cannot reconcile an empty journal")
            candidate_head = json.loads(lines[-1]).get("sha256")
            if not isinstance(candidate_head, str):
                fail("journal candidate head is invalid")
            journal, proof = open_authenticated_chat(
                paths["journal"], spiral_source_root=args.spiral_root,
                chat_session_id="bridge-forward-reconcile",
                mission_id=args.mission_id, objective=manifest["objective"],
                terminal_outcome=manifest["terminal_outcome"],
                integrity_key=secret, expected_head=candidate_head,
            )
            observed_heads = tuple(event["sha256"] for event in journal.events)
            if previous_head not in observed_heads:
                fail("anchored revision is not an ancestor of authenticated journal")
            appended = len(observed_heads) - 1 - observed_heads.index(previous_head)
            if appended:
                replace_anchor(paths["anchor"], {
                    "mission_id": args.mission_id, "head": candidate_head,
                })
            # A separate authenticated readback confirms the actual durable head,
            # not simply a successful rename or a previously held object.
            _, verified = open_authenticated_chat(
                paths["journal"], spiral_source_root=args.spiral_root,
                chat_session_id="bridge-forward-readback",
                mission_id=args.mission_id, objective=manifest["objective"],
                terminal_outcome=manifest["terminal_outcome"],
                integrity_key=secret, expected_head=candidate_head,
            )
            if verified.source_ref != "spiral-journal:" + candidate_head:
                fail("reconciliation readback is not source-matched")
            # Reopen the persisted anchor, not only the authenticated journal.
            persisted_anchor = json.loads(read_bytes(paths["anchor"]))
            if persisted_anchor != {"mission_id": args.mission_id, "head": candidate_head}:
                fail("reconciled anchor readback does not match authenticated journal")
            print(json.dumps({
                "status": "VERIFIED_RECONCILED" if appended else "VERIFIED_UNCHANGED",
                "mission_id": verified.mission_id, "previous_head": previous_head,
                "head": candidate_head, "authenticated_events_recovered": appended,
                "session_id": verified.chat_session_id,
                "automatic_chatgpt_host_hook_verified": False,
            }))
            return
        journal, recovery = open_authenticated_chat(
            paths["journal"], spiral_source_root=args.spiral_root, 
            chat_session_id=(args.session_id if args.command in ("recover", "admit", "dispatch") else "bridge-update"),
            mission_id=args.mission_id, objective=manifest["objective"],
            terminal_outcome=manifest["terminal_outcome"],
            integrity_key=secret, expected_head=anchor["head"]
        )
        if args.command in ("recover", "admit", "dispatch"):
            verified_fact_keys = tuple(dict.fromkeys(
                event["data"]["key"] for event in journal.events
                if event["kind"] in ("verified_fact", "superseded_fact")
            ))
            recovery = recover_existing_chat_session(journal, args.session_id,
                                                      fact_keys=verified_fact_keys)
            if args.command == "recover":
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
            if args.command == "dispatch":
                # Only a pre-registered, non-mutating operation is exposed here.
                # This callback consumes actual recovered state and produces a
                # verifiable continuation plan, never an external side effect.
                def continue_from_cursor(state):
                    return {
                        "next_cursor": state.cursor,
                        "binding": state.source_ref,
                        "instructions_to_apply": list(state.corrections),
                        "verified_facts": state.facts,
                        "objective": state.objective,
                    }
                def inspect_recovered_fact(state):
                    # A persisted inspect:<fact-key> cursor selects a sourced fact.
                    # No inferred or unsourced fact is permitted as a fallback.
                    key = state.cursor.partition(":")[2]
                    if not key or key not in state.facts:
                        fail("requested verified fact is not present in recovered context")
                    fact = state.facts[key]
                    if not isinstance(fact, dict) or not fact.get("source"):
                        fail("recovered fact has no provenance")
                    return {
                        "key": key,
                        "fact": fact,
                        "binding": state.source_ref,
                        "instructions_to_apply": list(state.corrections),
                    }
                # Admit the authenticated recovery into the actual APEX context
                # gate before invoking the registered downstream callback.
                kernel = create_verified_runtime_kernel()
                snapshot = resume_authenticated_chat_in_apex(
                    kernel, recovery,
                    task_instruction=(
                        f"Continue mission {recovery.mission_id} from "
                        f"{recovery.source_ref} at cursor {recovery.cursor}"
                    ),
                    target_state=recovery.terminal_outcome,
                    operation_class="chat_context_admission",
                    applied_to_action=bool(recovery.material_context_found),
                    expected_mission_id=args.mission_id,
                )
                receipt = execute_recovered_action(
                    recovery,
                    expected_mission_id=args.mission_id,
                    expected_source_ref="spiral-journal:" + anchor["head"],
                    registry={
                        "continue": continue_from_cursor,
                        "inspect": inspect_recovered_fact,
                    },
                )
                print(json.dumps({
                    "status": "RECOVERED_ACTION_DISPATCHED",
                    "mission_id": receipt.mission_id,
                    "head": anchor["head"],
                    "action_name": receipt.action_name,
                    "apex_runtime_id": snapshot.runtime_id,
                    "apex_phase": snapshot.phase,
                    "apex_receipt_kinds": list(snapshot.receipt_kinds),
                    "cursor": receipt.cursor,
                    "result": receipt.result,
                    "downstream_action_executed": True,
                    "external_side_effect_executed": False,
                    "automatic_chatgpt_host_hook_verified": False,
                }, indent=2))
                return
            kernel = create_verified_runtime_kernel()
            applied = bool(recovery.material_context_found)
            snapshot = resume_authenticated_chat_in_apex(
                kernel,
                recovery,
                task_instruction=(
                    f"Continue mission {recovery.mission_id} from {recovery.source_ref} "
                    f"at cursor {recovery.cursor or 'initial'}"
                ),
                target_state=recovery.terminal_outcome,
                operation_class="chat_context_admission",
                applied_to_action=applied,
                expected_mission_id=args.mission_id,
            )
            print(json.dumps({
                "status": "APEX_CONTEXT_ADMITTED",
                "mission_id": recovery.mission_id,
                "objective": recovery.objective,
                "terminal_outcome": recovery.terminal_outcome,
                "session_id": recovery.chat_session_id,
                "head": anchor["head"],
                "source_ref": recovery.source_ref,
                "cursor": recovery.cursor,
                "corrections": list(recovery.corrections),
                "facts": recovery.facts,
                "apex_runtime_id": snapshot.runtime_id,
                "apex_phase": snapshot.phase,
                "apex_receipt_kinds": list(snapshot.receipt_kinds),
                "recovered_context_applied_to_apex_instruction": applied,
                "downstream_action_executed": False,
                "automatic_chatgpt_host_hook_verified": False,
            }, indent=2))
            return
        if args.command == "correct":
            journal.correct(args.instruction)
        elif args.command == "checkpoint":
            journal.checkpoint(args.cursor)
        elif args.command == "fact":
            journal.verify_fact(args.key, args.value, source=args.source)
        events = journal.events
        if not events:
            fail("journal mutation has no authenticated head")
        new_head = events[-1]["sha256"]
        replace_anchor(paths["anchor"], {"mission_id": args.mission_id, "head": new_head})
        # Independent readback from original adapter is mandatory.
        _, proof = open_authenticated_chat(
            paths["journal"], spiral_source_root=args.spiral_root, chat_session_id="bridge-write-readback",
            mission_id=args.mission_id, objective=manifest["objective"],
            terminal_outcome=manifest["terminal_outcome"], integrity_key=secret, expected_head=new_head)
        # Verify the independently persisted anchor as well as the authenticated
        # journal before acknowledging a mutation to the caller.
        persisted_anchor = json.loads(read_bytes(paths["anchor"]))
        if persisted_anchor != {"mission_id": args.mission_id, "head": new_head}:
            fail("updated anchor readback does not match authenticated journal")
        if proof.source_ref != "spiral-journal:" + new_head:
            fail("mutation readback is not source-matched")
        print(json.dumps({"status":"VERIFIED_UPDATE", "mission_id":proof.mission_id,
                          "head":new_head, "cursor":proof.cursor, "corrections_count":len(proof.corrections)}))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("FAIL_CLOSED: " + str(exc), file=sys.stderr)
        sys.exit(1)
