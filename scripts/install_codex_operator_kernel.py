#!/usr/bin/env python3
"""Install/update the GlacierEQ managed block in ~/.codex/AGENTS.md.

Preserves all non-managed existing AGENTS content, writes a local mirror of the
shared kernel, creates an exact-byte unique backup when AGENTS changes, and
prints SHA-256 receipts from the bytes that were actually persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path

BEGIN = "<!-- GLACIEREQ_OPERATOR_KERNEL:BEGIN -->"
END = "<!-- GLACIEREQ_OPERATOR_KERNEL:END -->"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of the exact bytes persisted at path."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_marker_layout(existing: str) -> None:
    """Reject incomplete, duplicated, or misordered managed-block markers."""
    begin_count = existing.count(BEGIN)
    end_count = existing.count(END)
    if begin_count == 0 and end_count == 0:
        return
    if begin_count != 1 or end_count != 1:
        raise ValueError(
            "AGENTS.md must contain either no GlacierEQ markers or exactly one BEGIN/END pair"
        )
    if existing.index(BEGIN) > existing.index(END):
        raise ValueError("AGENTS.md GlacierEQ markers are misordered")


def replace_managed_block(existing: str, managed: str) -> str:
    """Replace one valid managed block or prepend it when none exists."""
    validate_marker_layout(existing)
    managed = managed.strip() + "\n"
    if BEGIN in existing:
        before, rest = existing.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        return before.rstrip() + "\n\n" + managed + after.lstrip()
    if existing.strip():
        return managed + "\n" + existing.lstrip()
    return managed


def create_exact_backup(path: Path, destination_dir: Path) -> Path:
    """Create an exclusive exact-byte backup with a collision-resistant name."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = destination_dir / f"AGENTS.md.backup.{stamp}.{secrets.token_hex(4)}"
    with backup.open("xb") as handle:
        handle.write(path.read_bytes())
    return backup


def main() -> int:
    """Install the managed bootstrap and verify exact persisted state."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    codex_home = args.codex_home.expanduser().resolve()
    canonical = (repo_root / "GLACIEREQ_OPERATOR_KERNEL.md").read_text(encoding="utf-8")
    managed = (repo_root / "adapters/codex/GLOBAL_AGENTS_MANAGED_BLOCK.md").read_text(encoding="utf-8")

    codex_home.mkdir(parents=True, exist_ok=True)
    agents_path = codex_home / "AGENTS.md"
    mirror_path = codex_home / "GLACIEREQ_OPERATOR_KERNEL.md"

    existing = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    updated = replace_managed_block(existing, managed)

    if updated != existing:
        if agents_path.exists():
            backup = create_exact_backup(agents_path, codex_home)
            print(f"backup={backup}")
        agents_path.write_bytes(updated.encode("utf-8"))

    mirror_path.write_bytes(canonical.encode("utf-8"))

    readback_agents = agents_path.read_text(encoding="utf-8")
    readback_kernel = mirror_path.read_text(encoding="utf-8")
    if readback_agents != updated:
        raise RuntimeError("AGENTS.md readback verification failed")
    if readback_kernel != canonical:
        raise RuntimeError("kernel mirror readback verification failed")
    validate_marker_layout(readback_agents)

    print(f"agents={agents_path}")
    print(f"agents_sha256={sha256_file(agents_path)}")
    print(f"kernel={mirror_path}")
    print(f"kernel_sha256={sha256_file(mirror_path)}")
    print("status=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
