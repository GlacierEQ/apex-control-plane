import json

import pytest

from scripts import scan_repos
from scripts.scan_repos import (
    EstateRefreshError,
    build_public_artifacts,
    validate_payload,
    write_json,
)


def valid_payload(**overrides):
    payload = {
        "ok": True,
        "status": "refreshed",
        "snapshot_id": "11111111-1111-4111-8111-111111111111",
        "previous_snapshot_id": "22222222-2222-4222-8222-222222222222",
        "repository_count": 10,
        "original_count": 6,
        "fork_count": 4,
        "private_count": 3,
        "public_count": 7,
        "archived_count": 1,
        "family_counts": {"control_plane": 4, "other": 6},
        "lifecycle_counts": {"active": 8, "reference": 2},
        "delta": {
            "new": 1,
            "removed_or_transferred": 2,
            "renamed_or_transferred": 3,
            "state_changes": 4,
        },
        "inventory_root_sha256": "a" * 64,
        "canonical_candidate_count": 3,
        "verified_canonical_count": 2,
        "ignition_queue_count": 10,
        "scan_mode": "metadata_only",
        "github_writes": 0,
        "token_persisted": False,
    }
    payload.update(overrides)
    return payload


def test_validate_payload_accepts_redacted_receipt():
    receipt = validate_payload(valid_payload())
    assert receipt["redacted"] is True
    assert receipt["repository_count"] == 10
    assert receipt["inventory_root_sha256"] == "a" * 64


def test_validate_payload_rejects_repository_details():
    payload = valid_payload()
    payload["repositories"] = [{"full_name": "GlacierEQ/private-repo"}]
    with pytest.raises(EstateRefreshError, match="not_redacted"):
        validate_payload(payload)


def test_validate_payload_rejects_inconsistent_original_fork_counts():
    with pytest.raises(EstateRefreshError, match="original_fork"):
        validate_payload(valid_payload(original_count=5))


def test_validate_payload_rejects_inconsistent_visibility_counts():
    with pytest.raises(EstateRefreshError, match="visibility"):
        validate_payload(valid_payload(private_count=4))


def test_validate_payload_rejects_bad_inventory_hash():
    with pytest.raises(EstateRefreshError, match="inventory_root"):
        validate_payload(valid_payload(inventory_root_sha256="abc"))


def test_validate_payload_rejects_incomplete_delta_contract():
    with pytest.raises(EstateRefreshError, match="invalid_delta"):
        validate_payload(valid_payload(delta={"new": 1}))


def test_validate_payload_rejects_family_count_mismatch():
    with pytest.raises(EstateRefreshError, match="family_counts"):
        validate_payload(valid_payload(family_counts={"other": 9}))


def test_public_artifacts_contain_no_repository_list():
    receipt = validate_payload(valid_payload())
    registry, delta, scan = build_public_artifacts(receipt)
    encoded = json.dumps([registry, delta, scan])
    assert "repositories" not in encoded
    assert "private-repo" not in encoded
    assert delta["detail_location"] == "private Supabase Repo Atlas snapshot"


def test_atomic_write_produces_complete_json(tmp_path):
    path = tmp_path / "nested" / "receipt.json"
    payload = {"schema_version": 2, "redacted": True, "snapshot_id": "safe"}
    write_json(path, payload)
    assert json.loads(path.read_text()) == payload
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_oidc_endpoint_rejects_non_actions_host(monkeypatch):
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://example.com/token")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "opaque-request-token")
    with pytest.raises(EstateRefreshError, match="endpoint_rejected"):
        scan_repos._oidc_token()
