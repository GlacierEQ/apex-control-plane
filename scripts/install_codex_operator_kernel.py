#!/usr/bin/env python3
"""Install/update the GlacierEQ managed block in ~/.codex/AGENTS.md.

Preserves all non-managed existing AGENTS content, writes a local mirror of the
shared kernel, creates a timestamped backup when AGENTS changes, and prints
SHA-256 receipts for readback.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from datetime import datetime, timezone

BEGIN = "<!-- GLACIEREQ_OPERATOR_KERNEL:BEGIN -->"
END = "<!-- GLACIEREQ_OPERATOR_KERNEL:END -->"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_managed_block(existing: str, managed: str) -> str:
    managed = managed.strip() + "\n"
    if BEGIN in existing and END in existing:
        before, rest = existing.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        return before.rstrip() + "\n\n" + managed + after.lstrip()
    if existing.strip():
        return managed + "\n" + existing.lstrip()
    return managed


def main() -> int:
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
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = codex_home / f"AGENTS.md.backup.{stamp}"
            backup.write_text(existing, encoding="utf-8")
            print(f"backup={backup}")
        agents_path.write_text(updated, encoding="utf-8")

    mirror_path.write_text(canonical, encoding="utf-8")

    readback_agents = agents_path.read_text(encoding="utf-8")
    readback_kernel = mirror_path.read_text(encoding="utf-8")
    assert BEGIN in readback_agents and END in readback_agents
    assert readback_kernel == canonical

    print(f"agents={agents_path}")
    print(f"agents_sha256={sha256_text(readback_agents)}")
    print(f"kernel={mirror_path}")
    print(f"kernel_sha256={sha256_text(readback_kernel)}")
    print("status=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
