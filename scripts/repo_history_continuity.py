from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SUSPECT_CLASSES = {
    "DEFAULT_BRANCH_CHANGED",
    "HEAD_DISAPPEARED",
    "PRIOR_HEAD_UNREACHABLE",
    "REVIEW_REQUIRED",
    "REWRITE_SUSPECT",
    "ROLLBACK_SUSPECT",
}


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SystemExit(f"History continuity returned invalid {label}")
    return value


def validate_result(result: dict[str, object]) -> tuple[int, int]:
    allowed = {
        "ok",
        "status",
        "snapshot_id",
        "previous_snapshot_id",
        "changed_head_count",
        "suspect_count",
        "classifications",
        "github_writes",
        "token_persisted",
    }
    unexpected = sorted(set(result) - allowed)
    if unexpected:
        raise SystemExit(
            f"History continuity returned unexpected fields: {unexpected}"
        )
    if result.get("ok") is not True or result.get("status") not in {
        "audited",
        "already_audited",
    }:
        raise SystemExit("History continuity did not report a successful audit")
    if result.get("github_writes") != 0:
        raise SystemExit("History continuity reported a GitHub write")
    if result.get("token_persisted") is not False:
        raise SystemExit("History continuity reported credential persistence")

    for key in ("snapshot_id", "previous_snapshot_id"):
        value = result.get(key)
        if not isinstance(value, str) or not value:
            raise SystemExit(f"History continuity returned invalid {key}")

    changed = _nonnegative_int(result.get("changed_head_count"), "changed_head_count")
    classifications = result.get("classifications")
    if not isinstance(classifications, dict):
        raise SystemExit("History continuity returned invalid classifications")

    total = 0
    derived_suspects = 0
    for name, raw_count in classifications.items():
        if not isinstance(name, str) or not name:
            raise SystemExit("History continuity returned an invalid classification name")
        count = _nonnegative_int(raw_count, f"classification count for {name}")
        total += count
        if name in SUSPECT_CLASSES:
            derived_suspects += count
    if total != changed:
        raise SystemExit(
            "History continuity classification totals do not match changed heads"
        )

    supplied_suspects = result.get("suspect_count")
    if supplied_suspects is not None:
        supplied = _nonnegative_int(supplied_suspects, "suspect_count")
        if supplied != derived_suspects:
            raise SystemExit(
                "History continuity suspect count disagrees with classifications"
            )
    return changed, derived_suspects


def main() -> None:
    audience = "apex-repo-history-continuity"
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    continuity_url = os.environ.get("REPO_HISTORY_CONTINUITY_URL", "")
    if not request_url or not request_token:
        raise SystemExit("GitHub OIDC environment is unavailable")
    if not continuity_url:
        raise SystemExit("History continuity endpoint is unavailable")

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
        continuity_url,
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
            f"History continuity audit failed with HTTP {error.code}: {payload}"
        ) from None

    if not isinstance(result, dict):
        raise SystemExit("History continuity returned a non-object response")
    changed, suspects = validate_result(result)

    Path("repo_history_continuity_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    classifications = result.get("classifications", {})
    print(
        "Estate history continuity verified: "
        f"changed_heads={changed} suspects={suspects} "
        f"classifications={json.dumps(classifications, sort_keys=True)} "
        "github_writes=0"
    )
    if suspects:
        print(
            "::warning title=Estate history continuity anomalies::"
            f"{suspects} default-branch transition(s) require forensic review. "
            "This observer records evidence and does not block repository writes."
        )


if __name__ == "__main__":
    main()
