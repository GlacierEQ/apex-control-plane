import pytest

from evidence_location_history import (
    LocatorObservation,
    LocationContinuityError,
    build_locator_transition,
    classify_transition,
    continuity_match,
    transfer_verification_status,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def obs(**overrides):
    base = {
        "evidence_id": "EVD-123",
        "provider": "dropbox",
        "provider_file_id": "id:file-1",
        "provider_revision": "rev-1",
        "locator": "ns:1//Matter/receipt.pdf",
        "display_locator": "/Matter/receipt.pdf",
        "filename": "receipt.pdf",
        "byte_size": 100,
        "sha256": HASH_A,
        "observed_at": "2026-08-22T23:00:00+00:00",
    }
    base.update(overrides)
    return LocatorObservation(**base)


def test_move_does_not_change_evidence_identity():
    before = obs()
    after = obs(
        locator="ns:1//Archive/receipt.pdf",
        display_locator="/Archive/receipt.pdf",
        observed_at="2026-08-23T00:00:00+00:00",
    )

    assert classify_transition(before, after) == "moved"
    assert continuity_match(before, after) == "verified_content_continuity"
    receipt = build_locator_transition(before, after)
    assert receipt["evidence_id"] == "EVD-123"
    assert receipt["verification"] == "verified"


def test_cross_provider_transfer_with_equal_hash_is_verified():
    before = obs()
    after = obs(
        provider="google_drive",
        provider_file_id="gdrive-9",
        locator="drive://legal/receipt.pdf",
        observed_at="2026-08-23T01:00:00+00:00",
    )

    assert classify_transition(before, after) == "transfer_verified"
    assert build_locator_transition(before, after)["verification"] == "verified"


def test_cross_provider_transfer_without_hash_stays_pending():
    before = obs(sha256=None)
    after = obs(
        provider="google_drive",
        provider_file_id="gdrive-9",
        locator="drive://legal/receipt.pdf",
        sha256=None,
    )

    assert classify_transition(before, after) == "transfer_pending"
    assert transfer_verification_status(None, None) == "pending"


def test_hash_mismatch_breaks_silent_continuity():
    before = obs(sha256=HASH_A)
    after = obs(sha256=HASH_B, locator="ns:1//Archive/receipt.pdf")

    assert continuity_match(before, after) == "content_conflict"
    with pytest.raises(LocationContinuityError):
        classify_transition(before, after)


def test_rename_is_history_not_identity():
    before = obs()
    after = obs(
        locator="ns:1//Matter/receipt-original.pdf",
        display_locator="/Matter/receipt-original.pdf",
        filename="receipt-original.pdf",
    )

    assert classify_transition(before, after) == "renamed"
    assert continuity_match(before, after) == "verified_content_continuity"


def test_same_hash_different_evidence_ids_is_duplicate_candidate():
    before = obs(evidence_id="EVD-A")
    after = obs(evidence_id="EVD-B", provider_file_id="id:file-2")

    assert continuity_match(before, after) == "verified_content_duplicate"


def test_invalid_sha256_is_rejected():
    with pytest.raises(ValueError):
        obs(sha256="not-a-hash")
