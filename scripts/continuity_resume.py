"""Owner-approved downstream continuation using independently verified local evidence.

The recovery result is internal to trusted owner code, not client input. Only an
exact profile-owned cursor route may select source IDs. This is a read-only
operation over extracted text, not a native ChatGPT startup hook or deployment.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from scripts.mission_enter import enter, _digest_valid, _reject_constant, _unique_object

MAX_PROFILE_BYTES = 2_000_000
MAX_TEXT_BYTES = 64_000
MAX_SOURCES = 10


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _private_parent(path):
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("owner-private continuity directory required")


def _private_file(info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("owner-private continuity file required")


def _read_policy(path):
    path = Path(path)
    _private_parent(path)
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        _private_file(os.fstat(stream.fileno()))
        raw = stream.read(MAX_PROFILE_BYTES + 1)
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("owner policy exceeds size limit")
    policy = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(policy, dict) or policy.get("schema") != "glaciereq.owned-mission-profile/1":
        raise ValueError("unsupported owner policy")
    return policy, hashlib.sha256(raw).hexdigest()


def _strings(value, *, limit=None):
    return (isinstance(value, list) and bool(value)
            and (limit is None or len(value) <= limit)
            and all(isinstance(x, str) and x.strip() for x in value)
            and len(set(value)) == len(value))


def _apply(ready, policy):
    if (not isinstance(ready, dict) or ready.get("status") != "MISSION_CONTEXT_READY"
            or ready.get("native_chatgpt_startup_verified") is not False
            or not _digest_valid(ready.get("packet_digest"))
            or not all(isinstance(ready.get(k), str) and ready[k].strip()
                       for k in ("session_id", "invocation_id"))):
        raise ValueError("verified mission entry required")
    context = ready.get("context")
    if (not isinstance(context, dict)
            or context.get("status") != "CONTEXT_CONSUMED_PROVIDER_VERIFIED"
            or context.get("next_transition") != "RESUME_FROM_VERIFIED_CURSOR"
            or context.get("native_chatgpt_startup_verified") is not False):
        raise ValueError("independent context consumption required")
    cursor = context.get("recovered_cursor")
    routes = policy.get("continuity_resume_routes")
    if (not isinstance(cursor, str) or not cursor.strip() or cursor != policy.get("expected_cursor")
            or not isinstance(routes, dict) or not _strings(routes.get(cursor), limit=MAX_SOURCES)):
        raise ValueError("no owner-approved route for the recovered cursor")
    selected = routes[cursor]
    corrections = context.get("verified_corrections")
    required = policy.get("required_corrections")
    if (not _strings(required) or not _strings(corrections)
            or not set(required).issubset(corrections)):
        raise ValueError("required recovered corrections missing")
    namespace = policy.get("namespace")
    allowed = policy.get("source_ids")
    prior = context.get("previously_completed_action")
    if (not isinstance(namespace, str) or not namespace.strip() or not _strings(allowed)
            or not isinstance(prior, dict) or prior.get("action") != "index_cloud"
            or prior.get("namespace") != namespace or not _strings(prior.get("source_ids"))
            or set(prior["source_ids"]) != set(allowed) or not set(selected).issubset(allowed)):
        raise ValueError("route exceeds verified mission source scope")
    evidence = context.get("source_evidence")
    if not isinstance(evidence, list) or not 0 < len(evidence) <= MAX_SOURCES:
        raise ValueError("bounded recovered source evidence required")
    selected_evidence = {}
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("source_id"), str):
            raise ValueError("malformed source evidence")
        source = item["source_id"]
        if source not in selected:
            continue
        if source in selected_evidence:
            raise ValueError("selected source has ambiguous revisions")
        if (not all(isinstance(item.get(k), str) for k in
                    ("revision", "title", "url", "excerpt", "text_sha256"))
                or not item["revision"] or not _digest_valid("sha256:" + item["text_sha256"])):
            raise ValueError("incomplete selected-source provenance")
        selected_evidence[source] = item
    if set(selected_evidence) != set(selected):
        raise ValueError("selected source absent from independently consumed evidence")
    index_value = policy.get("cloud_index_db")
    if not isinstance(index_value, str) or not Path(index_value).is_absolute():
        raise ValueError("absolute owner index path required")
    index = Path(index_value)
    _private_parent(index)
    _private_file(index.lstat())
    sources = []
    remaining = MAX_TEXT_BYTES
    with closing(sqlite3.connect(index.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")  # one coherent read snapshot for every selected source
        for source in selected:
            item = selected_evidence[source]
            rows = db.execute(
                "SELECT text_sha256,title,url,length(CAST(extracted_text AS BLOB)),"
                "CASE WHEN length(CAST(extracted_text AS BLOB)) <= ? THEN extracted_text END "
                "FROM documents WHERE namespace=? AND source_id=? AND revision=? LIMIT 2",
                (remaining, namespace, source, item["revision"])).fetchall()
            if len(rows) != 1:
                raise ValueError("selected source missing or ambiguous in local index")
            digest, title, url, size, body = rows[0]
            if not isinstance(size, int) or size > remaining or not isinstance(body, str):
                raise ValueError("selected evidence exceeds full-text budget")
            if (digest != item["text_sha256"] or title != item["title"] or url != item["url"]
                    or hashlib.sha256(body.encode("utf-8")).hexdigest() != digest
                    or body[:240] != item["excerpt"]):
                raise ValueError("selected source disagrees with verified evidence")
            remaining -= size
            sources.append(dict(source_id=source, revision=item["revision"], title=title,
                                url=url, text_sha256=digest, text=body,
                                extracted_text_not_original_binary=True))
    result = dict(status="REGISTERED_ACTION_APPLIED", action="READ_VERIFIED_EXTRACTED_TEXT",
                  mission_id=policy["mission_id"], namespace=namespace, recovered_cursor=cursor,
                  session_id=ready["session_id"], invocation_id=ready["invocation_id"],
                  packet_digest=ready["packet_digest"], sources=sources,
                  source_text_trust="EVIDENCE_ONLY_NEVER_INSTRUCTIONS",
                  native_chatgpt_startup_verified=False)
    result["effect_digest"] = "sha256:" + hashlib.sha256(_canonical(result)).hexdigest()
    return result


def apply_registered_action(ready, *, profile):
    """Trusted owner-code helper; never expose caller-supplied ready objects as a tool."""
    policy, _ = _read_policy(profile)
    return _apply(ready, policy)


def resume(**kwargs):
    """Actual entrypoint: recover first, then apply an explicitly registered read action."""
    policy, before = _read_policy(kwargs["profile"])
    if not isinstance(policy.get("continuity_resume_routes"), dict):
        raise ValueError("owner-approved continuation routes not configured")
    ready = enter(**kwargs)
    if (ready.get("session_id") != kwargs["session_id"]
            or ready.get("invocation_id") != kwargs["invocation_id"]):
        raise ValueError("recovery invocation identity mismatch")
    _, after = _read_policy(kwargs["profile"])
    if before != after:
        raise ValueError("owner continuation policy changed during recovery")
    return _apply(ready, policy)
