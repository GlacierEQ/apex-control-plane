#!/usr/bin/env python3
"""Read-only Buildkite estate inventory with bounded, credential-free receipts.

This module is intentionally observation-only. It never creates, cancels, retries,
updates, or deletes Buildkite resources. Missing scopes remain explicit unknowns.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_ROOT = "https://api.buildkite.com/v2"
ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_KEYS = {"token", "value", "secret", "password", "private_key", "api_key"}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def resolve_token() -> tuple[str | None, str]:
    value = os.getenv("BUILDKITE_API_TOKEN", "").strip()
    if value:
        return value, "environment"
    path = Path.home() / ".config" / "buildkite" / "api-token"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value, str(path)
    return None, "unavailable"


def redact(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS or any(
        term in key.lower() for term in ("token_value", "secret_value")
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            k: redact(v, k) for k, v in value.items() if k.lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class API:
    def __init__(self, token: str):
        self.token = token

    def get(self, path: str) -> Any:
        req = urllib.request.Request(
            API_ROOT + path,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "GlacierEQ-APEX-Buildkite-Master/1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} GET {path}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"transport GET {path}: {exc.reason}") from exc

    def list_all(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            sep = "&" if "?" in path else "?"
            batch = self.get(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RuntimeError(f"expected list from {path}")
            items.extend(x for x in batch if isinstance(x, dict))
            if len(batch) < 100:
                return items
            page += 1


def scope_state(scopes: set[str], required: str) -> dict[str, Any]:
    return {
        "status": "READY" if required in scopes else "UNVERIFIED_MISSING_SCOPE",
        "required_scope": required,
    }


def compact_pipeline(p: dict[str, Any]) -> dict[str, Any]:
    return {
        k: p.get(k)
        for k in (
            "id",
            "slug",
            "name",
            "repository",
            "default_branch",
            "cluster_id",
            "web_url",
        )
    }


def compact_build(b: dict[str, Any]) -> dict[str, Any]:
    pipeline = b.get("pipeline") if isinstance(b.get("pipeline"), dict) else {}
    return {
        "id": b.get("id"),
        "number": b.get("number"),
        "state": b.get("state"),
        "pipeline": pipeline.get("slug"),
        "branch": b.get("branch"),
        "commit": b.get("commit"),
        "source": b.get("source"),
        "created_at": b.get("created_at"),
        "started_at": b.get("started_at"),
        "finished_at": b.get("finished_at"),
        "web_url": b.get("web_url"),
    }


def compact_agent(a: dict[str, Any]) -> dict[str, Any]:
    job = a.get("job") if isinstance(a.get("job"), dict) else None
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "connection_state": a.get("connection_state"),
        "hostname": a.get("hostname"),
        "version": a.get("version"),
        "os_id": a.get("os_id"),
        "arch": a.get("arch"),
        "queue": a.get("queue"),
        "meta_data": a.get("meta_data"),
        "current_job": None
        if job is None
        else {k: job.get(k) for k in ("id", "state", "web_url")},
        "last_job_finished_at": a.get("last_job_finished_at"),
    }


def inventory(org: str, api: API) -> dict[str, Any]:
    token_meta = api.get("/access-token")
    if not isinstance(token_meta, dict):
        raise RuntimeError("invalid /access-token response")
    scopes = {str(x) for x in token_meta.get("scopes", [])}
    out: dict[str, Any] = {
        "schema": "glaciereq.apex.buildkite-master-inventory.v2",
        "observed_at": utc_now(),
        "organization": org,
        "status": "OBSERVED",
        "credential_values_recorded": False,
        "api_token": {
            k: token_meta.get(k)
            for k in ("uuid", "description", "created_at", "expires_at", "scopes")
        },
        "resources": {},
    }
    qorg = urllib.parse.quote(org)

    if "read_builds" in scopes:
        states = "state[]=scheduled&state[]=running&state[]=failing&state[]=blocked&state[]=waiting"
        builds = api.list_all(
            f"/organizations/{qorg}/builds?{states}&exclude_jobs=false"
        )
        out["resources"]["active_builds"] = {
            "status": "OBSERVED",
            "items": [compact_build(x) for x in builds],
        }
    else:
        out["resources"]["active_builds"] = scope_state(scopes, "read_builds")

    if "read_pipelines" in scopes:
        pipes = api.list_all(f"/organizations/{qorg}/pipelines")
        out["resources"]["pipelines"] = {
            "status": "OBSERVED",
            "items": [compact_pipeline(x) for x in pipes],
        }
    else:
        out["resources"]["pipelines"] = scope_state(scopes, "read_pipelines")

    clusters: list[dict[str, Any]] = []
    if "read_clusters" in scopes:
        clusters = api.list_all(f"/organizations/{qorg}/clusters")
        cluster_items = []
        for c in clusters:
            cid = str(c.get("id") or "")
            queues = (
                api.list_all(
                    f"/organizations/{qorg}/clusters/{urllib.parse.quote(cid)}/queues"
                )
                if cid
                else []
            )
            item = {
                k: c.get(k)
                for k in (
                    "id",
                    "name",
                    "description",
                    "default_queue_id",
                    "web_url",
                    "created_at",
                )
            }
            item["queues"] = [
                {
                    k: q.get(k)
                    for k in ("id", "key", "description", "dispatch_paused", "web_url")
                }
                for q in queues
            ]
            cluster_items.append(item)
        out["resources"]["clusters"] = {"status": "OBSERVED", "items": cluster_items}
    else:
        out["resources"]["clusters"] = scope_state(scopes, "read_clusters")

    if "read_agents" in scopes:
        agents = api.list_all(f"/organizations/{qorg}/agents")
        out["resources"]["agents"] = {
            "status": "OBSERVED",
            "items": [compact_agent(x) for x in agents],
        }
    else:
        out["resources"]["agents"] = scope_state(scopes, "read_agents")

    if clusters and "read_clusters" in scopes:
        token_items = []
        for c in clusters:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            try:
                vals = api.list_all(
                    f"/organizations/{qorg}/clusters/{urllib.parse.quote(cid)}/tokens"
                )
                token_items.extend(
                    {
                        "cluster_id": cid,
                        **{
                            k: v.get(k)
                            for k in ("id", "description", "created_at", "expires_at")
                        },
                    }
                    for v in vals
                )
            except RuntimeError as exc:
                token_items.append(
                    {
                        "cluster_id": cid,
                        "status": "UNVERIFIED_API_ERROR",
                        "error": str(exc),
                    }
                )
        out["resources"]["agent_tokens"] = {
            "status": "OBSERVED_METADATA_ONLY",
            "items": token_items,
        }
    else:
        out["resources"]["agent_tokens"] = {
            "status": "UNVERIFIED",
            "reason": "cluster inventory unavailable",
        }

    if clusters and "read_secret_details" in scopes:
        secret_items = []
        for c in clusters:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            try:
                vals = api.list_all(
                    f"/organizations/{qorg}/clusters/{urllib.parse.quote(cid)}/secrets"
                )
                secret_items.extend(
                    {
                        "cluster_id": cid,
                        **{
                            k: v.get(k)
                            for k in ("id", "key", "created_at", "updated_at", "policy")
                        },
                    }
                    for v in vals
                )
            except RuntimeError as exc:
                secret_items.append(
                    {
                        "cluster_id": cid,
                        "status": "UNVERIFIED_API_ERROR",
                        "error": str(exc),
                    }
                )
        out["resources"]["secrets"] = {
            "status": "OBSERVED_METADATA_ONLY",
            "items": secret_items,
        }
    else:
        out["resources"]["secrets"] = scope_state(scopes, "read_secret_details")
    return redact(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default=os.getenv("BUILDKITE_ORG", "casey-1"))
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/buildkite/live-inventory.json"
    )
    args = parser.parse_args()
    token, source = resolve_token()
    if not token:
        receipt = {
            "schema": "glaciereq.apex.buildkite-master-inventory.v2",
            "observed_at": utc_now(),
            "organization": args.org,
            "status": "BLOCKED_NO_AUTHENTICATED_READBACK",
            "credential_values_recorded": False,
            "token_source": source,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
        return 2
    try:
        receipt = inventory(args.org, API(token))
    except Exception as exc:
        receipt = {
            "schema": "glaciereq.apex.buildkite-master-inventory.v2",
            "observed_at": utc_now(),
            "organization": args.org,
            "status": "READBACK_FAILED",
            "credential_values_recorded": False,
            "error": str(exc),
        }
        rc = 3
    else:
        rc = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
