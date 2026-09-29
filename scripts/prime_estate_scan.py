#!/usr/bin/env python3
"""Classify PRIME-bearing files without blanket replacement.

Input is the durable GitHub inventory emitted by the estate sweep. This scanner
does not delete or rewrite sources. It identifies likely semantic classes so a
later repair can open and counter-engineer only harmful occurrences.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "artifacts" / "prime_estate_inventory_2026-09-28.json"


def classify_path(row: dict[str, Any]) -> str:
    path = str(row.get("path", "")).lower()
    if "legacy/" in path or "backup" in path or "archive" in path:
        return "HISTORICAL_PROVENANCE"
    if path.endswith((".json", ".yaml", ".yml")) and "prime_directive" in path:
        return "MECHANICAL_GATE"
    if "prime_directive_enforcer" in path or "prime_directive_boot" in path:
        return "MECHANICAL_GATE"
    if "casebuilder" in path or "case_spine" in path:
        return "DOMAIN_PRIME"
    if path.endswith("agents.md") or path.endswith("agent_system_prompt.md"):
        return "UNKNOWN"
    return "UNKNOWN"


def main() -> int:
    data = json.loads(DEFAULT_INVENTORY.read_text(encoding="utf-8"))
    rows = []
    counts: dict[str, int] = {}
    for item in data.get("files", []):
        semantic_class = classify_path(item)
        counts[semantic_class] = counts.get(semantic_class, 0) + 1
        rows.append({**item, "preclassification": semantic_class})
    out = {
        "source_inventory": str(DEFAULT_INVENTORY.relative_to(ROOT)),
        "classification_semantics": (
            "preclassification only; governing/executable UNKNOWN files must be opened "
            "before any mutation"
        ),
        "counts": counts,
        "files": rows,
    }
    target = ROOT / "artifacts" / "prime_estate_preclassification_2026-09-28.json"
    target.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
