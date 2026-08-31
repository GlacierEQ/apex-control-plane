import hashlib
import json

import pytest

from jack.src.casebuilder_forge import (
    REQUIRED_ARTIFACTS,
    build_casebuilder_invocation,
    build_verified_jack_action,
    validate_forge_receipt,
    validate_invocation_argv,
)
from jack.src.jack_relentless_gate import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    GateState,
    validate_receipt,
)


def _forge_fixture(tmp_path):
    state = {
        "case_id": "CASE-JACK",
        "sources": {
            "SRC-CHAT": {
                "id": "SRC-CHAT",
                "source_class": 3,
                "native": False,
                "metadata": {"original_chat_source": True},
            }
        },
        "actors": {},
        "facts": {},
        "events": {},
        "elements": {},
        "allegations": {
            "ALG-1": {"id": "ALG-1", "status": "hardened"},
            "ALG-K": {"id": "ALG-K", "status": "killed"},
        },
        "gaps": {},
        "discovery_targets": {},
        "contradictions": {},
        "knowledge": {},
        "damages": {},
        "accountability_paths": {},
        "cross_exam_blocks": {},
        "allegation_links": {},
        "kill_tests": {
            "ALG-K": {
                "allegation_id": "ALG-K",
                "survives": False,
                "disposition": "kill",
            }
        },
    }

    for name in REQUIRED_ARTIFACTS:
        path = tmp_path / name
        if name == "case_state.json":
            path.write_text(
                json.dumps(state, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(f"fixture:{name}\n", encoding="utf-8")

    artifacts = []
    for name in REQUIRED_ARTIFACTS:
        path = tmp_path / name
        artifacts.append(
            {
                "path": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "byte_size": path.stat().st_size,
            }
        )

    counts = {
        "sources": 1,
        "actors": 0,
        "facts": 0,
        "events": 0,
        "elements": 0,
        "allegations": 2,
        "contradictions": 0,
        "knowledge_nodes": 0,
        "damages": 0,
        "gaps": 0,
        "discovery_targets": 0,
        "accountability_paths": 0,
        "cross_exam_blocks": 0,
        "allegation_links": 0,
        "kill_tests": 1,
        "anchor_allegations": 1,
    }
    receipt = {
        "schema": "casebuilder4000.build-receipt.v2",
        "case_id": "CASE-JACK",
        "generated_at": "2026-08-31T00:00:00Z",
        "counts": counts,
        "validation_errors": [],
        "output_files": list(REQUIRED_ARTIFACTS),
        "artifacts": artifacts,
    }
    return receipt, state


def _all_true():
    return {
        name: True
        for name in GateState.__dataclass_fields__
    }


def _jack_receipt(action):
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "authority": "OPERATOR_INTENT",
        "task": "forge current legal case",
        "objective": "build source-bound allegation architecture",
        "canonical_owner": "GlacierEQ/apex-control-plane",
        "sources_opened": [
            {
                "system": "Casebuilder4000",
                "object_id": "CASE-JACK",
                "opened": True,
            }
        ],
        "actions_executed": [action],
        "verification": [
            {
                "check": "casebuilder readback",
                "receipt_ref": action["provider_receipt"],
                "passed": True,
            }
        ],
        "persistence_receipts": [action["provider_receipt"]],
        "readback_receipts": [action["provider_receipt"]],
        "gates": _all_true(),
        "status": "COMPLETE",
        "exact_blockers": [],
        "resolved_blockers": [],
        "next_material_action": "continue case hardening",
    }


def test_packet_or_receipt_structure_alone_is_not_verified_execution(tmp_path):
    receipt, _ = _forge_fixture(tmp_path)
    proof = validate_forge_receipt(receipt)
    assert proof["structure_valid"] is True
    assert proof["readback_verified"] is False


def test_exact_artifact_readback_builds_verified_jack_action(tmp_path):
    receipt, _ = _forge_fixture(tmp_path)
    action = build_verified_jack_action(
        receipt,
        output_dir=tmp_path,
    )
    assert action["executed"] is True
    assert action["verified"] is True
    assert action["state"] == "VERIFIED"
    assert action["case_development_state"] == "ANCHOR_BUILT"
    assert action["provider_receipt"].startswith(
        "casebuilder:CASE-JACK:"
    )
    validate_receipt(_jack_receipt(action))


def test_tampered_artifact_cannot_validate(tmp_path):
    receipt, _ = _forge_fixture(tmp_path)
    (tmp_path / "max_impact_report.md").write_text(
        "tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash mismatch|size mismatch"):
        build_verified_jack_action(
            receipt,
            output_dir=tmp_path,
        )


def test_missing_required_output_cannot_validate(tmp_path):
    receipt, _ = _forge_fixture(tmp_path)
    receipt["output_files"].remove("contradiction_matrix.csv")
    with pytest.raises(ValueError, match="missing required outputs"):
        validate_forge_receipt(receipt)


def test_killed_allegation_must_remain_visible_as_killed(tmp_path):
    receipt, state = _forge_fixture(tmp_path)
    state["allegations"]["ALG-K"]["status"] = "hardened"
    path = tmp_path / "case_state.json"
    path.write_text(
        json.dumps(state, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    case_row = next(
        row
        for row in receipt["artifacts"]
        if row["path"] == "case_state.json"
    )
    case_row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    case_row["byte_size"] = path.stat().st_size

    with pytest.raises(ValueError, match="was not preserved as killed"):
        validate_forge_receipt(receipt, output_dir=tmp_path)


def test_derived_chat_cannot_self_promote_to_primary_proof(tmp_path):
    receipt, state = _forge_fixture(tmp_path)
    state["sources"]["SRC-CHAT"]["source_class"] = 0
    path = tmp_path / "case_state.json"
    path.write_text(
        json.dumps(state, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    case_row = next(
        row
        for row in receipt["artifacts"]
        if row["path"] == "case_state.json"
    )
    case_row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    case_row["byte_size"] = path.stat().st_size

    with pytest.raises(ValueError, match="promoted above derived-analysis"):
        validate_forge_receipt(receipt, output_dir=tmp_path)


def test_invocation_is_argv_safe_and_has_no_shell_promotion():
    argv = build_casebuilder_invocation(
        "packet.json",
        "build/case",
    )
    assert argv == (
        "casebuilder",
        "build",
        "--input",
        "packet.json",
        "--out",
        "build/case",
    )
    validate_invocation_argv(argv)
    with pytest.raises(ValueError):
        validate_invocation_argv(
            (
                "casebuilder",
                "build",
                "--input",
                "packet.json\nrm -rf /",
                "--out",
                "build/case",
            )
        )
