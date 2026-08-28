import json
import shutil
from pathlib import Path

import pytest

from forensic_integrity import (
    AcquisitionReceipt,
    IntegrityError,
    SourceObservation,
    build_observation_manifest,
    custody_event_hash,
    recipe_hash,
    stable_evidence_id,
    verify_manifest,
)


def test_stable_evidence_id_survives_provider_revision_changes():
    a = stable_evidence_id("dropbox", "id:abc", "rev1")
    b = stable_evidence_id("dropbox", "id:abc", "rev1")
    c = stable_evidence_id("dropbox", "id:abc", "rev2")
    assert a == b == c
    assert a.startswith("EVD-")


def test_observation_manifest_is_deterministic_given_time():
    obs = [
        SourceObservation(
            source_provider="dropbox",
            source_file_id="id:z",
            source_revision=None,
            source_path="ns:1//z.txt",
            original_filename="z.txt",
            byte_size=2,
            observed_at="2026-08-22T23:00:00+00:00",
        ),
        SourceObservation(
            source_provider="dropbox",
            source_file_id="id:a",
            source_revision="r1",
            source_path="ns:1//a.txt",
            original_filename="a.txt",
            byte_size=1,
            observed_at="2026-08-22T23:00:00+00:00",
        ),
    ]
    one = build_observation_manifest(
        obs,
        matter_id="MAT-1",
        scope={"path": "/pilot"},
        generated_at="2026-08-22T23:00:00+00:00",
    )
    two = build_observation_manifest(
        reversed(obs),
        matter_id="MAT-1",
        scope={"path": "/pilot"},
        generated_at="2026-08-22T23:00:00+00:00",
    )
    assert one == two
    assert verify_manifest(one)
    tampered = json.loads(json.dumps(one))
    tampered["items"][0]["byte_size"] = 999
    assert not verify_manifest(tampered)


def test_acquisition_receipt_rejects_hash_mismatch(tmp_path: Path):
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"original")
    dst.write_bytes(b"changed!")
    with pytest.raises(IntegrityError):
        AcquisitionReceipt.from_paths(
            evidence_id="EVD-test",
            source_path=src,
            destination_path=dst,
            method="copy",
            tool_name="pytest",
            tool_version="1",
        )


def test_acquisition_receipt_verifies_exact_copy(tmp_path: Path):
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"same bytes")
    shutil.copyfile(src, dst)
    receipt = AcquisitionReceipt.from_paths(
        evidence_id="EVD-test",
        source_path=src,
        destination_path=dst,
        method="copy",
        tool_name="pytest",
        tool_version="1",
    )
    assert receipt.verified is True
    assert receipt.source_hash == receipt.destination_hash
    assert receipt.byte_size == len(b"same bytes")


def test_recipe_hash_ignores_mapping_order():
    assert recipe_hash({"b": 2, "a": 1}) == recipe_hash({"a": 1, "b": 2})


def test_custody_hash_chains():
    p1 = {"action": "observe", "evidence_id": "EVD-1"}
    h1 = custody_event_hash(None, p1)
    h2 = custody_event_hash(h1, {"action": "acquire", "evidence_id": "EVD-1"})
    assert h1 != h2
    assert custody_event_hash(None, p1) == h1
