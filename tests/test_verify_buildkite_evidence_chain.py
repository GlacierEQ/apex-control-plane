from __future__ import annotations

import hashlib
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.verify_buildkite_evidence_chain import (
    build_receipt,
    parse_evidence,
    verify_evidence,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_verified_evidence_rehashes_downloaded_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "source.xml"
    artifact.write_bytes(b"source-bearing-ci-evidence")
    rows = verify_evidence(
        [
            f"operator_fidelity=source-fidelity:{artifact}:{_digest(artifact.read_bytes())}"
        ]
    )
    assert rows[0]["verification_state"] == "bytes_rehashed_match_build_metadata"
    assert rows[0]["producer_step"] == "source-fidelity"


def test_metadata_hash_cannot_self_certify_different_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "source.xml"
    artifact.write_bytes(b"actual")
    forged = _digest(b"different")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_evidence([f"operator_fidelity=source-fidelity:{artifact}:{forged}"])


def test_missing_downloaded_artifact_is_not_evidence_absence(tmp_path: Path) -> None:
    missing = tmp_path / "missing.xml"
    with pytest.raises(FileNotFoundError, match="artifact missing"):
        verify_evidence([f"operator_fidelity=source-fidelity:{missing}:{'0' * 64}"])


def test_duplicate_evidence_identity_is_rejected(tmp_path: Path) -> None:
    artifact = tmp_path / "source.xml"
    artifact.write_bytes(b"same")
    spec = f"gate=source-fidelity:{artifact}:{_digest(artifact.read_bytes())}"
    with pytest.raises(ValueError, match="duplicate evidence identity"):
        verify_evidence([spec, spec])


def test_malformed_digest_is_rejected_before_verification() -> None:
    with pytest.raises(ValueError, match="malformed"):
        parse_evidence("gate=source-fidelity:/tmp/a:not-a-digest")


def test_receipt_rejects_checkout_commit_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.verify_buildkite_evidence_chain.current_head", lambda: "actual-head"
    )
    args = Namespace(
        expected_commit="expected-head",
        branch="feature",
        build_id="build-id",
        build_number="1",
        pipeline="apex-control-plane",
    )
    with pytest.raises(ValueError, match="checkout commit mismatch"):
        build_receipt(args, [])


def test_cli_writes_receipt_and_digest_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import verify_buildkite_evidence_chain as module

    artifact = tmp_path / "evidence.bin"
    artifact.write_bytes(b"verified")
    receipt = tmp_path / "receipt.json"
    sums = tmp_path / "SHA256SUMS"
    monkeypatch.setattr(module, "current_head", lambda: "head-sha")
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: Namespace(
            expected_commit="head-sha",
            branch="feature",
            build_id="build-id",
            build_number="9",
            pipeline="apex-control-plane",
            output=receipt,
            sums_output=sums,
            evidence=[
                f"gate=source-fidelity:{artifact}:{_digest(artifact.read_bytes())}"
            ],
        ),
    )
    assert module.main() == 0
    assert receipt.is_file()
    manifest = sums.read_text()
    assert _digest(artifact.read_bytes()) in manifest
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() in manifest
