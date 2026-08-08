"""Refresh the private Repo Atlas through GitHub Actions OIDC.

The full repository inventory never enters this public repository. The broker
returns only aggregate counts, snapshot identifiers, and a hash-bound receipt.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIENCE = "apex-repo-atlas-estate-refresh"
BROKER_URL = (
    "https://dyhprklicgewmrimecey.supabase.co/functions/v1/"
    "apex-github-oidc-estate-atlas-refresh"
)
MAX_RESPONSE_BYTES = 128 * 1024
REGISTRY_PATH = Path(os.environ.get("REPO_REGISTRY_PATH", "repo_registry.json"))
DELTA_PATH = Path(os.environ.get("REPO_DELTA_PATH", "repo_registry_delta.json"))
SCAN_PATH = Path(os.environ.get("REPO_SCAN_PATH", "repo_scan.json"))
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
DELTA_KEYS = (
    "new",
    "removed_or_transferred",
    "renamed_or_transferred",
    "state_changes",
)
COUNT_KEYS = (
    "repository_count",
    "original_count",
    "fork_count",
    "private_count",
    "public_count",
    "archived_count",
    "canonical_candidate_count",
    "verified_canonical_count",
    "ignition_queue_count",
)
ALLOWED_TOP_LEVEL = {
    "ok",
    "status",
    "snapshot_id",
    "previous_snapshot_id",
    *COUNT_KEYS,
    "family_counts",
    "lifecycle_counts",
    "delta",
    "inventory_root_sha256",
    "scan_mode",
    "github_writes",
    "token_persisted",
}


class EstateRefreshError(RuntimeError):
    """Fail-closed refresh error without credential or private-repository data."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise EstateRefreshError("redirect_rejected")


_NO_REDIRECT_OPENER = urllib.request.build_opener(_RejectRedirects())


def _request_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except EstateRefreshError:
        raise
    except urllib.error.HTTPError as error:
        raise EstateRefreshError(f"http_{error.code}") from error
    except urllib.error.URLError as error:
        raise EstateRefreshError("transport_failed") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise EstateRefreshError("response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EstateRefreshError("invalid_json") from error
    if not isinstance(payload, dict):
        raise EstateRefreshError("invalid_payload")
    return payload


def _oidc_token() -> str:
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "").strip()
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "").strip()
    if not request_url or not request_token:
        raise EstateRefreshError("github_oidc_environment_unavailable")
    parsed = urllib.parse.urlsplit(request_url)
    hostname = (parsed.hostname or "").lower()
    suffix = ".actions.githubusercontent.com"
    subdomain = hostname[: -len(suffix)] if hostname.endswith(suffix) else ""
    if (
        parsed.scheme != "https"
        or not hostname.endswith(suffix)
        or not subdomain
        or subdomain.startswith(".")
        or subdomain.endswith(".")
    ):
        raise EstateRefreshError("github_oidc_endpoint_rejected")
    separator = "&" if "?" in request_url else "?"
    url = f"{request_url}{separator}{urllib.parse.urlencode({'audience': AUDIENCE})}"
    payload = _request_json(
        urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {request_token}"},
            method="GET",
        )
    )
    value = payload.get("value")
    if not isinstance(value, str) or value.count(".") != 2:
        raise EstateRefreshError("github_oidc_token_invalid")
    return value


def _broker_refresh(oidc_token: str) -> dict[str, Any]:
    body = json.dumps({}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        BROKER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {oidc_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return _request_json(request)


def _nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EstateRefreshError(f"invalid_{key}")
    return value


def _count_map(payload: dict[str, Any], key: str, repository_count: int) -> dict[str, int]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise EstateRefreshError(f"invalid_{key}")
    output: dict[str, int] = {}
    for name, count in value.items():
        if not isinstance(name, str) or not name or isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise EstateRefreshError(f"invalid_{key}")
        output[name] = count
    if sum(output.values()) != repository_count:
        raise EstateRefreshError(f"inconsistent_{key}")
    return dict(sorted(output.items()))


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    unexpected = set(payload) - ALLOWED_TOP_LEVEL
    if unexpected:
        raise EstateRefreshError("broker_response_not_redacted")
    if payload.get("ok") is not True or payload.get("status") != "refreshed":
        raise EstateRefreshError("refresh_not_confirmed")
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not UUID_RE.fullmatch(snapshot_id):
        raise EstateRefreshError("invalid_snapshot_id")
    previous_snapshot_id = payload.get("previous_snapshot_id")
    if previous_snapshot_id is not None and (
        not isinstance(previous_snapshot_id, str) or not UUID_RE.fullmatch(previous_snapshot_id)
    ):
        raise EstateRefreshError("invalid_previous_snapshot_id")

    counts = {key: _nonnegative_int(payload, key) for key in COUNT_KEYS}
    if counts["original_count"] + counts["fork_count"] != counts["repository_count"]:
        raise EstateRefreshError("inconsistent_original_fork_counts")
    if counts["private_count"] + counts["public_count"] != counts["repository_count"]:
        raise EstateRefreshError("inconsistent_visibility_counts")
    if counts["archived_count"] > counts["repository_count"]:
        raise EstateRefreshError("inconsistent_archived_count")
    if counts["verified_canonical_count"] > counts["canonical_candidate_count"]:
        raise EstateRefreshError("inconsistent_canonical_counts")
    if counts["ignition_queue_count"] > 25:
        raise EstateRefreshError("invalid_ignition_queue_count")

    family_counts = _count_map(payload, "family_counts", counts["repository_count"])
    lifecycle_counts = _count_map(payload, "lifecycle_counts", counts["repository_count"])
    delta_value = payload.get("delta")
    if not isinstance(delta_value, dict) or set(delta_value) != set(DELTA_KEYS):
        raise EstateRefreshError("invalid_delta")
    delta = {key: _nonnegative_int(delta_value, key) for key in DELTA_KEYS}

    inventory_root = payload.get("inventory_root_sha256")
    if not isinstance(inventory_root, str) or not HEX64_RE.fullmatch(inventory_root):
        raise EstateRefreshError("invalid_inventory_root")
    if payload.get("scan_mode") != "metadata_only":
        raise EstateRefreshError("invalid_scan_mode")
    if payload.get("github_writes") != 0 or payload.get("token_persisted") is not False:
        raise EstateRefreshError("unsafe_broker_receipt")

    return {
        "schema_version": 2,
        "redacted": True,
        "source": "supabase_repo_atlas_oidc_refresh",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": snapshot_id,
        "previous_snapshot_id": previous_snapshot_id,
        **counts,
        "family_counts": family_counts,
        "lifecycle_counts": lifecycle_counts,
        "delta": delta,
        "inventory_root_sha256": inventory_root.lower(),
        "scan_mode": "metadata_only",
        "github_writes": 0,
        "token_persisted": False,
        "private_repository_metadata_persisted_here": False,
    }


def build_public_artifacts(receipt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = dict(receipt)
    delta = {
        "schema_version": 2,
        "redacted": True,
        "snapshot_id": receipt["snapshot_id"],
        "previous_snapshot_id": receipt["previous_snapshot_id"],
        "generated_at": receipt["generated_at"],
        "delta": dict(receipt["delta"]),
        "inventory_root_sha256": receipt["inventory_root_sha256"],
        "detail_location": "private Supabase Repo Atlas snapshot",
    }
    scan = {
        "schema_version": 2,
        "redacted": True,
        "snapshot_id": receipt["snapshot_id"],
        "generated_at": receipt["generated_at"],
        "total": receipt["repository_count"],
        "originals": receipt["original_count"],
        "forks": receipt["fork_count"],
        "private": receipt["private_count"],
        "public": receipt["public_count"],
        "archived": receipt["archived_count"],
        "family_counts": dict(receipt["family_counts"]),
        "lifecycle_counts": dict(receipt["lifecycle_counts"]),
        "inventory_root_sha256": receipt["inventory_root_sha256"],
    }
    return registry, delta, scan


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> int:
    oidc_token = ""
    try:
        oidc_token = _oidc_token()
        payload = _broker_refresh(oidc_token)
        oidc_token = ""
        receipt = validate_payload(payload)
        registry, delta, scan = build_public_artifacts(receipt)
        write_json(REGISTRY_PATH, registry)
        write_json(DELTA_PATH, delta)
        write_json(SCAN_PATH, scan)
    except (EstateRefreshError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")), file=sys.stderr)
        return 1
    finally:
        oidc_token = ""

    print(
        json.dumps(
            {
                "ok": True,
                "snapshot_id": registry["snapshot_id"],
                "repository_count": registry["repository_count"],
                "original_count": registry["original_count"],
                "fork_count": registry["fork_count"],
                "delta": registry["delta"],
                "inventory_root_sha256": registry["inventory_root_sha256"],
                "redacted": True,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
