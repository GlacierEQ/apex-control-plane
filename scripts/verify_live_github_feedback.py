"""Live GitHub-native feedback smoke for APEX's existing adaptive selector.

Runs only with a GitHub Actions token on the owning repository. It is a
domain-bounded proof of GitHub source mutation and learner readback, NOT proof
of an unrelated human mission outcome or cross-provider deployment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from contextlib import nullcontext
from hashlib import sha256
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.continuous_impact_selection import (  # noqa: E402
    ContinuousImpactSelector, ImpactAttempt, ImpactCandidate,
)


def github_get(repository: str, resource: str, token: str) -> dict:
    if not repository or "/" not in repository or not token:
        raise ValueError("GitHub repository and authenticated provider token required")
    url = f"https://api.github.com/repos/{repository}/{resource}"
    request = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(request, timeout=20) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("expected provider-native GitHub object")
    return value


def file_blob(repository: str, path: str, at: str, token: str) -> str | None:
    resource = f"contents/{quote(path, safe='/')}?ref={quote(at, safe='')}"
    try:
        value = github_get(repository, resource, token)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    blob = value.get("sha")
    return blob if isinstance(blob, str) and len(blob) == 40 else None


def prove_live_source_feedback(
    repository: str, commit_sha: str, token: str, *,
    model_state_path: str | Path | None = None,
) -> dict:
    """Verify one material code delta through GitHub's independent native API."""
    commit = github_get(repository, f"commits/{commit_sha}", token)
    if commit.get("sha") != commit_sha:
        raise ValueError("provider returned a different commit identity")
    parents = commit.get("parents") or []
    if not parents or not isinstance(parents[0].get("sha"), str):
        raise ValueError("live feedback requires a parent commit for comparison")
    parent_sha = parents[0]["sha"]

    candidate_file = next((
        item for item in commit.get("files", [])
        if isinstance(item, dict)
        and item.get("status") in {"added", "modified"}
        and isinstance(item.get("filename"), str)
        and item["filename"].startswith(("src/", "scripts/", ".github/workflows/"))
    ), None)
    if not candidate_file:
        return {"status": "NO_RELEVANT_CODE_DELTA", "commit": commit_sha}

    path = candidate_file["filename"]
    before_blob = file_blob(repository, path, parent_sha, token)
    after_blob = file_blob(repository, path, commit_sha, token)
    if not after_blob or after_blob == before_blob:
        raise ValueError("GitHub provider did not prove a material file mutation")

    objective = "Independently verify exact GitHub code delta and feed proven result to existing APEX learning"
    candidate = ImpactCandidate(
        candidate_id="github-native-code-delta",
        operation="Verify exact native GitHub code delta",
        operation_class="github_native_code_delta_verification",
        expected_delta="GitHub source blob differs from its parent and is readable by provider API",
        features={
            "mission_advancement": 0.6, "state_change_value": 0.6,
            "verification_strength": 1.0, "provenance_strength": 1.0,
            "operator_alignment": 0.9, "failure_risk": 0.05,
        },
        evidence_refs=(f"github:commit:{commit_sha}",),
    )
    temporary = TemporaryDirectory(prefix="apex-github-live-feedback-") if model_state_path is None else nullcontext(None)
    with temporary as folder:
        model_path = Path(model_state_path) if model_state_path is not None else Path(folder) / "verified-learning.json"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        # This is a bounded, non-sensitive continuity marker paired with the
        # existing learner. Validate source state before considering it applied.
        marker_path = model_path.with_name("github-feedback-checkpoint.json")
        if marker_path.exists():
            checkpoint = json.loads(marker_path.read_text(encoding="utf-8"))
            if (
                not isinstance(checkpoint, dict)
                or checkpoint.get("schema_version") != 1
                or not isinstance(checkpoint.get("applied_commits"), list)
                or not all(isinstance(value, str) and len(value) == 40 for value in checkpoint["applied_commits"])
            ):
                raise ValueError("incompatible persisted GitHub feedback checkpoint")
            if not model_path.is_file():
                raise ValueError("feedback checkpoint exists without its learned model")
            applied = list(checkpoint["applied_commits"])
        else:
            if model_path.is_file():
                raise ValueError("learned model exists without the matching feedback checkpoint")
            applied = []
        prior_model_restored = model_path.is_file()
        selector = ContinuousImpactSelector(model_state_path=model_path)
        decision = selector.select(
            task_id=f"github-native-feedback:{commit_sha}",
            mission=objective,
            operation_class=candidate.operation_class,
            state_version=f"github:parent:{parent_sha}",
            candidates=(candidate,),
        )
        attempt = ImpactAttempt(
            mission_sha256=decision.mission_sha256,
            candidate_id=candidate.candidate_id,
            method_id="github-provider-get-commit-and-file",
            source_state_ref=f"github:blob:{before_blob}" if before_blob else f"github:absent:{parent_sha}",
            stage="VERIFIED_MATERIAL_DELTA",
            provider_ref=f"github:commit:{commit_sha}",
            after_state_ref=f"github:blob:{after_blob}",
            readback_ref=f"github:blob:{after_blob}",
            source_class="source_native",
        )

        def independent_native_readback(receipt: ImpactAttempt) -> bool:
            reread_commit = github_get(repository, f"commits/{commit_sha}", token)
            reread_blob = file_blob(repository, path, commit_sha, token)
            return (
                reread_commit.get("sha") == commit_sha
                and reread_blob == after_blob
                and receipt.after_state_ref == f"github:blob:{reread_blob}"
                and receipt.source_state_ref != receipt.after_state_ref
            )

        previous = selector.engine.ranker.score(selector._to_adaptive(candidate)).score
        if commit_sha in applied:
            if not independent_native_readback(attempt):
                raise RuntimeError("cached learned commit failed provider-native readback")
            return {
                "status": "GITHUB_NATIVE_FEEDBACK_ALREADY_APPLIED",
                "commit": commit_sha, "path": path,
                "prior_model_restored": True,
                "duplicate_learning_prevented": True,
                "human_mission_complete": False,
            }
        selector.record_verified_outcome(
            decision=decision, candidates=(candidate,), success=True,
            reason="GitHub provider independently verified code delta at exact commit",
            provider_attempt=attempt,
            verify_native_readback=independent_native_readback,
        )
        restarted = ContinuousImpactSelector(model_state_path=model_path)
        learned = restarted.engine.ranker.score(restarted._to_adaptive(candidate)).score
        if not model_path.is_file() or not learned > previous:
            raise RuntimeError("verified feedback did not persist across selector instances")
        # Only record a completed provider readback. A crash before the marker
        # retains the valid model for recovery, rather than manufacturing proof.
        updated = {"schema_version": 1, "applied_commits": [*applied, commit_sha]}
        marker_path.write_text(json.dumps(updated, sort_keys=True) + "\n", encoding="utf-8")
        if json.loads(marker_path.read_text(encoding="utf-8")) != updated:
            raise RuntimeError("feedback checkpoint independent local readback failed")
    return {
        "status": "GITHUB_NATIVE_CODE_DELTA_VERIFIED",
        "commit": commit_sha, "path": path,
        "source_blob": before_blob,
        "readback_blob": after_blob,
        "model_reloaded": True,
        "prior_model_restored": prior_model_restored,
        "applied_commit_count": len(applied) + 1,
        "human_mission_complete": False,
    }


if __name__ == "__main__":
    repository = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    token = os.environ["GH_TOKEN"]
    persistent_model = os.environ.get("GLACIEREQ_APEX_LEARNING_STATE_PATH")
    result = prove_live_source_feedback(
        repository, sha, token,
        model_state_path=persistent_model if persistent_model else None,
    )
    print(json.dumps(result, sort_keys=True))
