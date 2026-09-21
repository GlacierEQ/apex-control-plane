#!/usr/bin/env python3
"""Validate GlacierEQ Operator Kernel projections and hardlock invariants."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_LAWS = [
    "RECOVER BEFORE RECREATING",
    "CONTINUE BEFORE RECONSTRUCTING",
    "COMPOUND BEFORE REPLACING",
    "A BLOCKED TOOL CHANGES THE ROUTE, NOT THE OBJECTIVE",
    "NO TOOL EVIDENCE -> NO EXECUTION CLAIM",
    "CONTEXT FIRST. SOURCE HYDRATION BEFORE SUBSTANTIVE REASONING. ANSWER LAST.",
    "REPEATED CORRECTIONS HARDEN FUTURE EXECUTION POLICY.",
]


def validate() -> list[str]:
    """Return surface-binding defects; an empty list means the contract is coherent."""
    errors: list[str] = []
    kernel = (ROOT / "GLACIEREQ_OPERATOR_KERNEL.md").read_text(encoding="utf-8")
    codex = (ROOT / "adapters/codex/GLOBAL_AGENTS_MANAGED_BLOCK.md").read_text(encoding="utf-8")
    project = (ROOT / "adapters/chatgpt/PROJECT_INSTRUCTIONS.md").read_text(encoding="utf-8")
    custom = (ROOT / "adapters/chatgpt/CUSTOM_INSTRUCTIONS.md").read_text(encoding="utf-8")
    bindings = json.loads((ROOT / "config/operator_kernel_surface_bindings_v1.json").read_text(encoding="utf-8"))

    for law in REQUIRED_LAWS:
        if law not in kernel:
            errors.append(f"kernel missing law: {law}")

    if "GLACIEREQ_OPERATOR_KERNEL:BEGIN" not in codex or "GLACIEREQ_OPERATOR_KERNEL:END" not in codex:
        errors.append("Codex managed block markers missing")
    if "If `~/.codex/skills/casey-operator-execution-kernel/SKILL.md` exists" not in codex:
        errors.append("Codex skill dependency must be conditional")

    for name, text in {"chatgpt_project": project, "chatgpt_custom": custom}.items():
        if "OpenAI system/developer instructions" not in text:
            errors.append(f"{name} missing platform authority boundary")
        lower = text.lower()
        if "context-first" not in lower and "context first" not in lower:
            errors.append(f"{name} missing standing hardlock fragment: context-first")
        for fragment in ("repeated corrections", "answer last", "recover"):
            if fragment not in lower:
                errors.append(f"{name} missing standing hardlock fragment: {fragment}")
        if "readback" not in lower and "read back" not in lower:
            errors.append(f"{name} missing recovery/readback contract")

    cc = bindings["canonical_contract"]
    if cc["path"] != "GLACIEREQ_OPERATOR_KERNEL.md":
        errors.append("surface binding canonical path mismatch")
    if bindings["codex"]["native_entrypoint"] != "~/.codex/AGENTS.md":
        errors.append("Codex native entrypoint mismatch")
    if not bindings["chatgpt"]["native_project_instructions_required_for_deterministic_project_bootstrap"]:
        errors.append("ChatGPT deterministic project bootstrap must require native Project Instructions")

    return errors


if __name__ == "__main__":
    problems = validate()
    if problems:
        for problem in problems:
            print(problem)
        raise SystemExit(1)
    print("operator-kernel-surfaces=valid")
