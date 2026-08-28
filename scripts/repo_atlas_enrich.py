from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main() -> None:
    audience = "apex-repo-atlas-estate-enrich"
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    enrich_url = os.environ.get("REPO_ATLAS_ENRICH_URL", "")
    if not request_url or not request_token:
        raise SystemExit("GitHub OIDC environment is unavailable")
    if not enrich_url:
        raise SystemExit("Repo Atlas enrichment URL is unavailable")

    separator = "&" if "?" in request_url else "?"
    oidc_request = urllib.request.Request(
        f"{request_url}{separator}audience={urllib.parse.quote(audience)}",
        headers={"Authorization": f"Bearer {request_token}"},
    )
    with urllib.request.urlopen(oidc_request, timeout=20) as response:
        oidc = json.loads(response.read()).get("value", "")
    if not oidc:
        raise SystemExit("GitHub OIDC token response was empty")
    print(f"::add-mask::{oidc}")

    request = urllib.request.Request(
        enrich_url,
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {oidc}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(
            f"Repo Atlas enrichment failed with HTTP {error.code}: {payload}"
        ) from None

    allowed = {
        "ok",
        "status",
        "snapshot_id",
        "receipt_id",
        "repository_count",
        "enriched_count",
        "default_head_count",
        "fork_lineage_count",
        "enrichment_root_sha256",
        "github_writes",
        "token_persisted",
    }
    unexpected = sorted(set(result) - allowed)
    if unexpected:
        raise SystemExit(
            f"Repo Atlas enrichment returned unexpected fields: {unexpected}"
        )
    if result.get("ok") is not True or result.get("status") not in {
        "enriched",
        "already_enriched",
    }:
        raise SystemExit("Repo Atlas enrichment did not report a successful result")
    if result.get("github_writes") != 0:
        raise SystemExit("Repo Atlas enrichment reported a GitHub write")
    if result.get("token_persisted") is not False:
        raise SystemExit("Repo Atlas enrichment reported credential persistence")

    refresh = json.loads(
        Path("repo_atlas_refresh_result.json").read_text(encoding="utf-8")
    )
    repository_count = result.get("repository_count")
    enriched_count = result.get("enriched_count")
    default_head_count = result.get("default_head_count")
    fork_lineage_count = result.get("fork_lineage_count")

    for label, value in (
        ("repository_count", repository_count),
        ("enriched_count", enriched_count),
        ("default_head_count", default_head_count),
        ("fork_lineage_count", fork_lineage_count),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SystemExit(f"Repo Atlas enrichment returned invalid {label}")

    if result.get("snapshot_id") != refresh.get("snapshot_id"):
        raise SystemExit("Repo Atlas enrichment did not bind to the refreshed snapshot")
    if repository_count != refresh.get("repository_count"):
        raise SystemExit("Repo Atlas enrichment repository count differs from refresh")
    if enriched_count != repository_count:
        raise SystemExit("Repo Atlas enrichment is incomplete")
    if fork_lineage_count != refresh.get("fork_count"):
        raise SystemExit("Repo Atlas fork lineage is incomplete")
    if default_head_count > repository_count:
        raise SystemExit("Repo Atlas default-head count exceeds repository count")

    root = result.get("enrichment_root_sha256")
    if not isinstance(root, str) or re.fullmatch(r"[0-9a-f]{64}", root) is None:
        raise SystemExit("Repo Atlas enrichment returned an invalid integrity root")

    Path("repo_atlas_enrichment_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Repo Atlas enrichment verified: "
        f"repositories={repository_count} "
        f"heads={default_head_count} "
        f"fork_lineage={fork_lineage_count} "
        f"github_writes={result.get('github_writes')}"
    )


if __name__ == "__main__":
    main()
