"""Progressive Pyramid source binding and startup proof boundary."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from apex_enforced_startup import build_apex_startup_request, load_apex_policy
from progressive_pyramid_source import resolve_pyramid_source, validate_pyramid_run


def _bundle(tmp_path: Path):
    path = tmp_path / "pyramid"
    path.mkdir()
    skill = "---\nname: progressive-pyramid\n---\n# Contract\n"
    contract = {"schema_id": "glaciereq.progressive-pyramid.contract.v1"}
    code = "import json\nprint(json.dumps({\'valid\':True,\'issues\':[]}))\n"
    (path / "SKILL.md").write_text(skill)
    (path / "progressive_pyramid.contract.json").write_text(json.dumps(contract))
    (path / "scripts").mkdir()
    (path / "scripts/validate_run.py").write_text(code)
    (path / ".source-commit").write_text("abc123")
    hashes = {name: hashlib.sha256((path/name).read_bytes()).hexdigest() for name in ("SKILL.md", "progressive_pyramid.contract.json", "scripts/validate_run.py")}
    lock = {"repository": "GlacierEQ/mega-skills", "commit": "abc123", "schema_id":contract["schema_id"], "sha256": hashes}
    return path, lock


def test_apex_startup_projects_pyramid_state_without_claiming_success(monkeypatch):
    policy = load_apex_policy()
    monkeypatch.setenv("PROGRESSIVE_PYRAMID_SKILL_DIR", "/missing/isolated/path")
    r = build_apex_startup_request(policy, task="deliver working system")
    assert r["progressive_pyramid"]["status"] == "UNAVAILABLE"
    assert r["requirements"]["pyramid_required_for_mission_completion"] is True
    assert r["progressive_pyramid"]["canonical_source"] == "GlacierEQ/mega-skills"


def test_source_lock_requires_exact_bytes(tmp_path):
    path, lock = _bundle(tmp_path)
    assert resolve_pyramid_source(lock, source_dir=path)["status"] == "LOADED"
    (path/"SKILL.md").write_text("tampered")
    assert resolve_pyramid_source(lock, source_dir=path)["status"] == "MISMATCH"


def test_missing_or_corrupt_source_never_promoted(tmp_path):
    path, lock = _bundle(tmp_path)
    assert resolve_pyramid_source(lock, source_dir=tmp_path/"absent")["status"] == "UNAVAILABLE"
    lock["commit"] = "wrong"
    assert resolve_pyramid_source(lock, source_dir=path)["status"] == "MISMATCH"


def test_terminal_claim_fails_without_proof_verifier(tmp_path):
    path, lock = _bundle(tmp_path)
    run={"center_point":{"status":"MISSION_COMPLETE","outcome_proofs":[{"criterion":"done","source_ref":"provider:receipt"}]},"acceptance_criteria":["done"]}
    assert validate_pyramid_run(run, lock, source_dir=path) != ()
    assert validate_pyramid_run(run, lock, source_dir=path, verifier=lambda c, r: True) == ()


def test_startup_source_missing_cannot_validate_terminal(tmp_path):
    _, lock = _bundle(tmp_path)
    assert validate_pyramid_run({"center_point":{"status":"MISSION_COMPLETE"}}, lock, source_dir=tmp_path/"absent")

def test_startup_receipt_cannot_self_certify_terminal_mission():
    from apex_enforced_startup import validate_apex_startup_receipt
    policy = load_apex_policy()
    receipt = {"apex_startup": {"mission_status": "MISSION_COMPLETE"}}
    errors = validate_apex_startup_receipt(policy, receipt)
    assert any("terminal" in error.lower() or "mission_complete" in error.lower()
               for error in errors)

def test_canonical_live_validation_of_inheritance_when_installed():
    from pathlib import Path
    root = Path.home()/".agents/skills/progressive-pyramid"
    if not root.is_dir():
        import pytest
        pytest.skip("canonical Skill not installed")
    lock = load_apex_policy()["progressive_pyramid_source"]
    stages=[]
    previous=None
    for label,version in [("corner_1_context","V1"),("corner_2_objective","V2"),
                          ("corner_3_constraints","V3"),("corner_4_resources","V4")]:
        ref=f"source:{version}"
        stages.append({"stage":label,"version":version,"artifact_ref":ref,"inherits":previous,
                       "verified_gains":["source-truth"]})
        previous=ref
    run={"protocol":lock["schema_id"],"mission_id":"test-mission",
         "original_outcome":"Verified external action",
         "recovered_sources":["source:case"],"acceptance_criteria":["target"],
         "stages":stages,"center_point":{"status":"ACTIVE"}}
    assert validate_pyramid_run(run,lock,source_dir=root) == ()
    run["stages"][2]["inherits"]="source:wrong"
    assert any("inheritance" in e for e in validate_pyramid_run(run,lock,source_dir=root))
