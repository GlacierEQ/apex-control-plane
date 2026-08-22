#!/usr/bin/env python3
"""Compatibility surface for the retired legacy daily audit engine.

All audit behavior delegates to ``src.audit_engine`` through ``apex_runner``. This
module remains importable for existing callers but is no longer scheduled separately.
"""
from __future__ import annotations

from dataclasses import asdict

import apex_runner

Finding = apex_runner.Finding


def _should_scan_secret_file(filename: str) -> bool:
    return apex_runner.should_scan_secret_file(filename)


def scan_secrets(root: str = ".") -> list[Finding]:
    return apex_runner.scan_for_secrets(root)


def detect_drift() -> list[Finding]:
    return apex_runner.detect_workflow_drift(".")


def validate_connectors() -> dict[str, dict]:
    results: dict[str, dict] = {}
    for status in apex_runner.validate_connectors():
        payload = asdict(status)
        payload["status"] = "AMBER" if status.reachable else "RED"
        results[status.name.casefold()] = payload
    return results


def main() -> int:
    return apex_runner.main([])


if __name__ == "__main__":
    raise SystemExit(main())
