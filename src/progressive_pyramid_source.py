"""Resolve the exact source of the shared Progressive Pyramid Skill."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

REPO = "GlacierEQ/mega-skills"
SCHEMA = "glaciereq.progressive-pyramid.contract.v1"
PARTS = ("SKILL.md", "progressive_pyramid.contract.json", "scripts/validate_run.py")

def default_source_dir() -> Path:
    value = os.environ.get("PROGRESSIVE_PYRAMID_SKILL_DIR")
    return Path(value).expanduser() if value else Path.home()/".agents/skills/progressive-pyramid"

def resolve_pyramid_source(lock: Mapping[str, Any], *, source_dir: Path | None = None) -> dict[str, Any]:
    """Report loaded only after matching revision, all three digests and schema."""
    base = {"canonical_source": REPO, "source_commit": lock.get("commit", ""), "schema_id": SCHEMA}
    if lock.get("repository") != REPO or lock.get("schema_id") != SCHEMA:
        return {**base, "status": "MISMATCH", "reason": "invalid source lock"}
    root = source_dir if source_dir is not None else default_source_dir()
    if not root.is_dir():
        return {**base, "status": "UNAVAILABLE", "reason": "Skill not installed"}
    try:
        rev = (root/".source-commit").read_text().strip()
    except OSError:
        return {**base, "status": "MISMATCH", "reason": "missing source revision"}
    if rev != lock.get("commit"):
        return {**base, "status": "MISMATCH", "reason": "wrong source revision"}
    for rel in PARTS:
        try:
            actual = hashlib.sha256((root/rel).read_bytes()).hexdigest()
        except OSError:
            return {**base, "status": "MISMATCH", "reason": f"missing {rel}"}
        if actual != lock.get("sha256", {}).get(rel):
            return {**base, "status": "MISMATCH", "reason": f"content mismatch: {rel}"}
    try:
        contract = json.loads((root/PARTS[1]).read_text())
    except (ValueError, OSError):
        return {**base, "status": "MISMATCH", "reason": "invalid JSON contract"}
    if contract.get("schema_id") != SCHEMA:
        return {**base, "status": "MISMATCH", "reason": "wrong contract schema"}
    return {**base, "status": "LOADED", "contract_sha256": lock["sha256"][PARTS[1]]}

def validate_pyramid_run(run: Mapping[str, Any], lock: Mapping[str, Any], *,
                         source_dir: Path | None = None, verifier=None) -> tuple[str, ...]:
    """Canonical CLI validates inheritance; host verifies external terminal proofs."""
    import subprocess
    import sys
    import tempfile
    state = resolve_pyramid_source(lock, source_dir=source_dir)
    if state["status"] != "LOADED":
        return (f"canonical Pyramid source is {state['status']}",)
    root = source_dir if source_dir is not None else default_source_dir()
    payload = json.loads(json.dumps(run))
    center = payload.get("center_point", {})
    terminal = center.get("status") == "MISSION_COMPLETE"
    if terminal:
        center["status"] = "ACTIVE"  # CLI has no provider-verifier injection
    with tempfile.TemporaryDirectory() as tmp:
        receipt_path = Path(tmp)/"run.json"
        receipt_path.write_text(json.dumps(payload))
        result = subprocess.run([sys.executable, str(root/PARTS[2]), str(receipt_path),
                                 "--contract", str(root/PARTS[1])],
                                capture_output=True, text=True, timeout=15, check=False)
    try:
        output = json.loads(result.stdout)
        errors = list(output["issues"])
    except (ValueError, KeyError, TypeError):
        errors = ["canonical validator did not return a valid result"]
    if result.returncode != 0 and not errors:
        errors.append("canonical validator process failed")
    if terminal:
        criteria = run.get("acceptance_criteria", [])
        proofs = center.get("outcome_proofs", [])
        seen = set()
        if not isinstance(criteria, list) or not isinstance(proofs, list):
            return tuple(errors + ["terminal acceptance or proof list missing"])
        for proof in proofs:
            if not isinstance(proof, dict):
                errors.append("malformed terminal proof")
                continue
            criterion, ref = proof.get("criterion"), proof.get("source_ref")
            if not isinstance(criterion, str) or criterion not in criteria or criterion in seen or not isinstance(ref,str) or not ref.strip():
                errors.append("terminal proof missing or duplicated")
                continue
            seen.add(criterion)
            if verifier is None or verifier(criterion, ref) is not True:
                errors.append(f"independent outcome proof failed: {criterion}")
        if seen != set(criteria) or not criteria:
            errors.append("terminal proof coverage incomplete")
    return tuple(errors)
