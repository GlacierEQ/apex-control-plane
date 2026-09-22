"""Jack specialist binding for Casebuilder4000.

Jack does not absorb the forge. It invokes the specialist, verifies its
receipt and exact artifacts, and exposes a verified action receipt to the
existing relentless execution gate.

A verified forge build is not the same thing as a complete legal case.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

CASEBUILDER_REPO = "GlacierEQ/Casebuilder4000"
CASE_CORPUS_REPO = "GlacierEQ/apex-legal-case"
SOURCE_ACQUISITION_REPO = "GlacierEQ/computer-user"
OUTPUT_RUNTIME_REPO = "GlacierEQ/legal-powerhouse"

RECEIPT_SCHEMA = "casebuilder4000.build-receipt.v2"

REQUIRED_ARTIFACTS = (
    "case_state.json",
    "master_fact_ledger.jsonl",
    "master_event_timeline.csv",
    "actor_index.csv",
    "element_matrix.csv",
    "allegation_matrix.csv",
    "contradiction_matrix.csv",
    "damages_ledger.csv",
    "discovery_targets.csv",
    "defense_matrix.csv",
    "accountability_matrix.csv",
    "allegation_links.csv",
    "cross_exam_blocks.jsonl",
    "actor_dossiers.json",
    "event_development_plan.json",
    "case_pressure_map.csv",
    "conversion_map.json",
    "max_impact_report.md",
)

COUNT_KEYS = (
    "sources",
    "actors",
    "facts",
    "events",
    "elements",
    "allegations",
    "contradictions",
    "knowledge_nodes",
    "damages",
    "gaps",
    "discovery_targets",
    "accountability_paths",
    "cross_exam_blocks",
    "allegation_links",
    "kill_tests",
    "anchor_allegations",
)

STATE_COUNT_KEYS = {
    "sources": "sources",
    "actors": "actors",
    "facts": "facts",
    "events": "events",
    "elements": "elements",
    "allegations": "allegations",
    "contradictions": "contradictions",
    "knowledge_nodes": "knowledge",
    "damages": "damages",
    "gaps": "gaps",
    "discovery_targets": "discovery_targets",
    "accountability_paths": "accountability_paths",
    "cross_exam_blocks": "cross_exam_blocks",
    "allegation_links": "allegation_links",
    "kill_tests": "kill_tests",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_casebuilder_invocation(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    executable: str = "casebuilder",
) -> tuple[str, ...]:
    """Return argv-safe invocation; never construct a shell command string."""
    exe = str(executable).strip()
    if not exe or "\n" in exe or "\r" in exe:
        raise ValueError("executable must be a non-empty argv token")
    return (
        exe,
        "build",
        "--input",
        str(Path(input_path)),
        "--out",
        str(Path(output_dir)),
    )


def load_forge_receipt(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("forge receipt root must be an object")
    return value


def _artifact_rows(receipt: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = receipt.get("artifacts")
    if not isinstance(rows, list):
        raise ValueError("forge receipt artifacts must be a list")
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("forge receipt artifact entries must be objects")
        name = row.get("path")
        if not isinstance(name, str) or not name:
            raise ValueError("forge receipt artifact path must be non-empty")
        if Path(name).name != name:
            raise ValueError(f"artifact path must be a basename: {name!r}")
        if name in indexed:
            raise ValueError(f"duplicate artifact receipt: {name}")
        digest = row.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError(f"artifact {name} has invalid sha256")
        size = row.get("byte_size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"artifact {name} has invalid byte_size")
        indexed[name] = row
    return indexed


def _validate_counts(receipt: Mapping[str, Any]) -> dict[str, int]:
    counts = receipt.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("forge receipt counts must be an object")
    normalized: dict[str, int] = {}
    for key in COUNT_KEYS:
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"forge receipt count {key!r} must be a non-negative int"
            )
        normalized[key] = value
    return normalized


def _load_case_state(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "case_state.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("case_state.json root must be an object")
    return value


def _validate_state_counts(
    counts: Mapping[str, int],
    state: Mapping[str, Any],
) -> None:
    for receipt_key, state_key in STATE_COUNT_KEYS.items():
        value = state.get(state_key)
        if not isinstance(value, dict):
            raise ValueError(f"case state {state_key!r} must be an object map")
        if len(value) != counts[receipt_key]:
            raise ValueError(
                f"case state count mismatch for {state_key}: "
                f"receipt={counts[receipt_key]} actual={len(value)}"
            )


def _validate_kill_visibility(state: Mapping[str, Any]) -> None:
    allegations = state.get("allegations", {})
    kill_tests = state.get("kill_tests", {})
    if not isinstance(allegations, dict) or not isinstance(kill_tests, dict):
        return
    for allegation_id, test in kill_tests.items():
        if not isinstance(test, dict):
            raise ValueError(f"kill test {allegation_id} must be an object")
        allegation = allegations.get(allegation_id)
        if not isinstance(allegation, dict):
            raise ValueError(
                "kill test references allegation absent from audit state: "
                + allegation_id
            )
        if (
            test.get("survives") is False
            and test.get("disposition") == "kill"
            and allegation.get("status") != "killed"
        ):
            raise ValueError(
                f"killed allegation {allegation_id} was not preserved as killed"
            )


def _validate_derived_chat_sources(state: Mapping[str, Any]) -> None:
    sources = state.get("sources", {})
    if not isinstance(sources, dict):
        return
    for source_id, source in sources.items():
        if not isinstance(source, dict):
            continue
        metadata = source.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if metadata.get("original_chat_source") is not True:
            continue
        if source.get("native") is True:
            continue
        source_class = source.get("source_class")
        if isinstance(source_class, bool) or not isinstance(source_class, int):
            raise ValueError(
                f"chat-derived source {source_id} has invalid source_class"
            )
        if source_class < 3:
            raise ValueError(
                f"derived chat source {source_id} was promoted above derived-analysis class"
            )


def validate_forge_receipt(
    receipt: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate build proof.

    Without an output_dir this validates only receipt structure. It does not
    authorize a VERIFIED Jack action. Exact artifact readback is required for
    that promotion.
    """
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ValueError(f"forge receipt schema must be {RECEIPT_SCHEMA}")
    case_id = receipt.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("forge receipt case_id must be non-empty")
    errors = receipt.get("validation_errors")
    if errors != []:
        raise ValueError("forge receipt must have validation_errors=[]")

    output_files = receipt.get("output_files")
    if not isinstance(output_files, list) or not all(
        isinstance(item, str) for item in output_files
    ):
        raise ValueError("forge receipt output_files must be a string list")
    missing_outputs = sorted(set(REQUIRED_ARTIFACTS) - set(output_files))
    if missing_outputs:
        raise ValueError(
            "forge receipt missing required outputs: " + ", ".join(missing_outputs)
        )

    counts = _validate_counts(receipt)
    artifacts = _artifact_rows(receipt)
    missing_artifacts = sorted(set(REQUIRED_ARTIFACTS) - set(artifacts))
    if missing_artifacts:
        raise ValueError(
            "forge receipt missing hash-bound artifacts: "
            + ", ".join(missing_artifacts)
        )

    result: dict[str, Any] = {
        "case_id": case_id,
        "receipt_sha256": _canonical_sha256(receipt),
        "structure_valid": True,
        "readback_verified": False,
        "case_development_state": (
            "ANCHOR_BUILT"
            if counts["anchor_allegations"] > 0
            else "ALLEGATIONS_DEVELOPING"
            if counts["allegations"] > 0
            else "INGESTED"
        ),
        "counts": counts,
    }

    if output_dir is None:
        return result

    root = Path(output_dir)
    for name in REQUIRED_ARTIFACTS:
        path = root / name
        if not path.is_file():
            raise ValueError(f"forge artifact missing at readback: {name}")
        expected = artifacts[name]
        actual_size = path.stat().st_size
        if actual_size != expected["byte_size"]:
            raise ValueError(
                f"forge artifact size mismatch for {name}: "
                f"receipt={expected['byte_size']} actual={actual_size}"
            )
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected["sha256"]:
            raise ValueError(f"forge artifact hash mismatch for {name}")

    state = _load_case_state(root)
    if state.get("case_id") != case_id:
        raise ValueError("case_state.json case_id disagrees with forge receipt")
    _validate_state_counts(counts, state)
    _validate_kill_visibility(state)
    _validate_derived_chat_sources(state)
    result["readback_verified"] = True
    return result


def build_verified_jack_action(
    receipt: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Promote only an exact read-back forge build to a Jack VERIFIED action."""
    proof = validate_forge_receipt(receipt, output_dir=output_dir)
    if proof["readback_verified"] is not True:
        raise ValueError("forge readback is required for VERIFIED action")
    return {
        "action": "casebuilder-forge",
        "target": proof["case_id"],
        "provider": CASEBUILDER_REPO,
        "provider_receipt": (
            f"casebuilder:{proof['case_id']}:{proof['receipt_sha256']}"
        ),
        "executed": True,
        "verified": True,
        "state": "VERIFIED",
        "case_development_state": proof["case_development_state"],
        "counts": proof["counts"],
        "nonclaims": [
            "verified forge build does not mean the legal case is complete",
            "derived analysis does not become native evidence by appearing in case state",
            "specialist verification does not confer project-direction authority",
        ],
    }


def validate_invocation_argv(argv: Sequence[str]) -> None:
    if not isinstance(argv, (list, tuple)) or len(argv) != 6:
        raise ValueError("Casebuilder invocation must contain exactly 6 argv tokens")
    if tuple(argv[1:3]) != ("build", "--input") or argv[4] != "--out":
        raise ValueError("Casebuilder invocation shape is invalid")
    for token in argv:
        if (
            not isinstance(token, str)
            or not token
            or "\n" in token
            or "\r" in token
        ):
            raise ValueError("Casebuilder invocation contains an invalid argv token")
