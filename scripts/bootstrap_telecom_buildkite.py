#!/usr/bin/env python3
"""Bootstrap and terminally verify Telecom on the existing APEX Buildkite fabric."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "reconcile_genius_buildkite.py"
RECEIPT_PATH = ROOT / "artifacts" / "buildkite" / "telecom-bootstrap.json"
RECEIPT_SHA_PATH = RECEIPT_PATH.with_suffix(RECEIPT_PATH.suffix + ".sha256")

TELECOM_BRANCH = "feat/telecom-foundation-boot-v1"
TELECOM_COMMIT = "651e51e2adc2e52e046e65362aa7c648c897fdd1"
TELECOM_SPEC = {
    "name": "Telecom-valley-atlas-cabin-solar",
    "slug": "telecom-valley-atlas-cabin-solar",
    "repository": "git@github.com:GlacierEQ/Telecom-valley-atlas-cabin-solar.git",
    "github_repository": "GlacierEQ/Telecom-valley-atlas-cabin-solar",
    "status_context": "buildkite/telecom-valley-atlas-cabin-solar",
    "pipeline_file": ".buildkite/pipeline.yml",
    "role": "telecommunications-domain",
}


def load_reconciler():
    spec = importlib.util.spec_from_file_location("apex_buildkite_reconciler", MODULE_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load APEX Buildkite reconciler")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def desired_telecom_pipeline(module, cluster_id: str) -> dict:
    return {
        "name": TELECOM_SPEC["name"],
        "slug": TELECOM_SPEC["slug"],
        "description": "GlacierEQ Telecommunications domain CI",
        "repository": TELECOM_SPEC["repository"],
        "cluster_id": cluster_id,
        "configuration": module.PIPELINE_UPLOAD_CONFIGURATION,
        "default_branch": TELECOM_BRANCH,
        "branch_configuration": None,
        "cancel_running_branch_builds": bool(
            module.REGISTRY["superseded_build_policy"]["cancel_running_branch_builds"]
        ),
        "skip_queued_branch_builds": bool(
            module.REGISTRY["superseded_build_policy"]["skip_queued_branch_builds"]
        ),
        "visibility": "private",
        "provider_settings": {
            "build_branches": True,
            "build_pull_requests": True,
            "build_pull_request_forks": False,
            "build_tags": False,
            "publish_commit_status": True,
            "publish_commit_status_per_step": True,
        },
    }


def reconcile_telecom_pipeline(api, module, pipelines: list[dict], cluster_id: str):
    existing = module.find_existing_pipeline(pipelines, TELECOM_SPEC)
    desired = desired_telecom_pipeline(module, cluster_id)
    org_path = f"/organizations/{urllib.parse.quote(module.ORG)}"
    if existing is None:
        created = api.request("POST", f"{org_path}/pipelines", desired)
        if not isinstance(created, dict) or not created.get("slug"):
            raise RuntimeError("Buildkite returned no Telecom pipeline slug")
        pipelines.append(created)
        return created, "CREATED"
    slug = str(existing["slug"])
    updated = api.request(
        "PATCH",
        f"{org_path}/pipelines/{urllib.parse.quote(slug)}",
        desired,
    )
    if not isinstance(updated, dict):
        raise RuntimeError("invalid Telecom Buildkite pipeline update response")
    return updated, "RECONCILED"


def verify_telecom_pipeline_readback(pipeline: dict, module, cluster_id: str) -> None:
    desired = desired_telecom_pipeline(module, cluster_id)
    failures: list[str] = []
    if module.normalize_repository(pipeline.get("repository")) != module.normalize_repository(
        TELECOM_SPEC["repository"]
    ):
        failures.append("repository")
    if str(pipeline.get("cluster_id") or "") != cluster_id:
        failures.append("cluster_id")
    if pipeline.get("default_branch") != TELECOM_BRANCH:
        failures.append("default_branch")
    if str(pipeline.get("description") or "") != desired["description"]:
        failures.append("description")
    for key in ("cancel_running_branch_builds", "skip_queued_branch_builds"):
        if bool(pipeline.get(key)) != bool(desired[key]):
            failures.append(key)
    if "buildkite-agent pipeline upload" not in str(pipeline.get("configuration") or ""):
        failures.append("configuration")
    if failures:
        raise RuntimeError(
            "Telecom Buildkite pipeline readback mismatch: " + ", ".join(failures)
        )


def trigger_telecom_build(api, module, slug: str) -> dict:
    payload = {
        "commit": TELECOM_COMMIT,
        "branch": TELECOM_BRANCH,
        "clean_checkout": True,
        "message": "APEX: verify Telecom on Buildkite",
        "env": {
            "APEX_EXECUTION_SURFACE": "buildkite",
            "APEX_TELECOM_BOOTSTRAP": "api-v1",
        },
        "meta_data": {
            "apex_mission": "telecom-ci-bootstrap",
            "source_repository": TELECOM_SPEC["github_repository"],
            "source_commit": TELECOM_COMMIT,
        },
    }
    path = (
        f"/organizations/{urllib.parse.quote(module.ORG)}/pipelines/"
        f"{urllib.parse.quote(slug)}/builds"
    )
    result = api.request("POST", path, payload)
    if not isinstance(result, dict) or result.get("number") is None:
        raise RuntimeError("Buildkite returned no Telecom build receipt")
    return result


def await_build(api, module, slug: str, number: int) -> dict:
    policy = module.REGISTRY["verification_policy"]
    success = {str(value) for value in policy["build_success_states"]}
    failure = {str(value) for value in policy["build_failure_states"]}
    deadline = time.monotonic() + float(policy["build_timeout_seconds"])
    interval = max(1.0, float(policy["poll_interval_seconds"]))
    path = (
        f"/organizations/{urllib.parse.quote(module.ORG)}/pipelines/"
        f"{urllib.parse.quote(slug)}/builds/{number}"
    )
    while True:
        build = api.request("GET", path)
        if not isinstance(build, dict):
            raise RuntimeError(f"invalid Buildkite build readback for {slug} #{number}")
        state = str(build.get("state") or "")
        if state in success:
            module.verify_returned_build_commit(build, TELECOM_COMMIT)
            if str(build.get("branch") or "") != TELECOM_BRANCH:
                raise RuntimeError(
                    f"Telecom Buildkite branch mismatch: {build.get('branch')!r}"
                )
            return build
        if state in failure:
            raise RuntimeError(f"Telecom Buildkite build failed: state={state}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for Telecom Buildkite build #{number}")
        time.sleep(interval)


def write_receipt(data: dict) -> None:
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    RECEIPT_PATH.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    RECEIPT_SHA_PATH.write_text(
        f"{digest}  {RECEIPT_PATH.name}\n",
        encoding="utf-8",
    )


def main() -> int:
    module = load_reconciler()
    token, token_source = module.resolve_buildkite_token()
    api = module.BuildkiteAPI(token)
    token_meta = module.inspect_api_token(api)
    cluster_id, cluster_source = module.resolve_cluster_id(api, token_meta)
    org_path = f"/organizations/{urllib.parse.quote(module.ORG)}"
    pipelines = module.list_all(api, f"{org_path}/pipelines")

    pipeline, mutation = reconcile_telecom_pipeline(
        api, module, pipelines, cluster_id
    )
    slug = str(pipeline["slug"])
    webhook = module.ensure_webhook(api, slug)
    readback = api.request("GET", f"{org_path}/pipelines/{urllib.parse.quote(slug)}")
    if not isinstance(readback, dict):
        raise RuntimeError("Telecom Buildkite pipeline readback failed")
    verify_telecom_pipeline_readback(readback, module, cluster_id)

    build = trigger_telecom_build(api, module, slug)
    module.verify_returned_build_commit(build, TELECOM_COMMIT)
    terminal = await_build(api, module, slug, int(build["number"]))

    receipt = {
        "schema": "glaciereq.apex.telecom-buildkite-bootstrap.v1",
        "status": "VERIFIED_TERMINAL_SUCCESS",
        "generated_at": module.utc_now(),
        "organization": module.ORG,
        "repository": TELECOM_SPEC["github_repository"],
        "branch": TELECOM_BRANCH,
        "source_commit": TELECOM_COMMIT,
        "mutation": mutation,
        "pipeline": module.compact_pipeline(readback),
        "webhook": webhook,
        "terminal_build": module.compact_build(terminal),
        "cluster": {
            "id": cluster_id,
            "source": cluster_source,
            "queue": module.DEFAULT_QUEUE,
        },
        "api_token": {
            "uuid": token_meta.get("uuid"),
            "description": token_meta.get("description"),
            "expires_at": token_meta.get("expires_at"),
            "source": token_source,
            "value_recorded": False,
        },
        "credentials_recorded": False,
    }
    write_receipt(receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"APEX Telecom Buildkite bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
