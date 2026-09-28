#!/usr/bin/env python3
"""Verify Buildkite upstream evidence bytes before issuing a CI receipt.

The receipt step must not trust a metadata hash as proof that the referenced
artifact exists or contains those bytes. Each evidence item names the producing
step, the downloaded artifact path, and the build-scoped metadata SHA-256. This
program recomputes the digest over the downloaded bytes and fails closed on any
mismatch before writing a PASS receipt.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file's exact bytes."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_evidence(spec: str) -> tuple[str, str, Path, str]:
    """Parse NAME=STEP:PATH:SHA256 without accepting ambiguous fields."""
    name, sep, rest = spec.partition("=")
    if not sep or not name.strip():
        raise ValueError("evidence must start with NAME=")
    step, sep, remainder = rest.partition(":")
    if not sep or not step.strip():
        raise ValueError(f"evidence {name!r} must include producing STEP")
    path_text, sep, expected = remainder.rpartition(":")
    if not sep or not path_text.strip():
        raise ValueError(f"evidence {name!r} must include artifact PATH")
    expected = expected.strip().lower()
    if not _SHA256_RE.fullmatch(expected):
        raise ValueError(f"evidence {name!r} expected SHA-256 is malformed")
    return name.strip(), step.strip(), Path(path_text), expected


def verify_evidence(specs: list[str]) -> list[dict[str, Any]]:
    """Independently hash every artifact and return only verified evidence."""
    if not specs:
        raise ValueError("at least one evidence item is required")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in specs:
        name, step, path, expected = parse_evidence(spec)
        if name in seen:
            raise ValueError(f"duplicate evidence identity: {name}")
        seen.add(name)
        if not path.is_file():
            raise FileNotFoundError(f"evidence artifact missing: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"evidence digest mismatch for {name}: expected {expected}, got {actual}"
            )
        rows.append(
            {
                "evidence_id": name,
                "producer_step": step,
                "artifact_path": path.as_posix(),
                "sha256": actual,
                "verification_state": "bytes_rehashed_match_build_metadata",
            }
        )
    return rows


def current_head() -> str:
    """Read the checkout HEAD used to issue this receipt."""
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def build_receipt(
    args: argparse.Namespace, evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    """Construct a receipt only after checkout and evidence verification pass."""
    head = current_head()
    if head != args.expected_commit:
        raise ValueError(
            f"checkout commit mismatch: expected {args.expected_commit}, got {head}"
        )
    return {
        "schema": "glaciereq.apex-control-plane.buildkite-evidence.v2",
        "status": "PASS",
        "commit": head,
        "branch": args.branch,
        "build_id": args.build_id,
        "build_number": args.build_number,
        "pipeline": args.pipeline,
        "generated_at": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "verification_model": "step-scoped artifact download + build-scoped metadata + independent local SHA-256 readback",
        "evidence": evidence,
    }


def parse_args() -> argparse.Namespace:
    """Parse the fail-closed receipt verifier command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--build-number", required=True)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sums-output", type=Path, required=True)
    parser.add_argument("--evidence", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    """Verify all evidence and atomically write a PASS receipt."""
    args = parse_args()
    evidence = verify_evidence(args.evidence)
    receipt = build_receipt(args, evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, args.output)

    lines = [f"{row['sha256']}  {row['artifact_path']}" for row in evidence]
    lines.append(f"{sha256_file(args.output)}  {args.output.as_posix()}")
    args.sums_output.parent.mkdir(parents=True, exist_ok=True)
    sums_tmp = args.sums_output.with_suffix(args.sums_output.suffix + ".tmp")
    sums_tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(sums_tmp, args.sums_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
