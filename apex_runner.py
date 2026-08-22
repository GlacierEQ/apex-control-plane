"""CLI for the evidence-led APEX audit engine."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import audit_engine as _engine

AuditInvariantError = _engine.AuditInvariantError
AuditReadback = _engine.AuditReadback
AuditRun = _engine.AuditRun
ConnectorStatus = _engine.ConnectorStatus
Finding = _engine.Finding
analyze_structure = _engine.analyze_structure
detect_workflow_drift = _engine.detect_workflow_drift
execute_audit = _engine.execute_audit
persist_run = _engine.persist_run
scan_for_secrets = _engine.scan_for_secrets
should_scan_secret_file = _engine.should_scan_secret_file
validate_connectors = _engine.validate_connectors
verify_run_receipt = _engine.verify_run_receipt

APEX_VERSION = "4.0.0-evidence-led"


def _default_run_id() -> str:
    configured = os.environ.get("RUN_DATE", "").strip()
    if configured:
        return configured
    return f"apex-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def _print_readback(readback: AuditReadback) -> None:
    print(
        json.dumps(
            {
                "event": "apex_audit_readback_verified",
                "run_id": readback.run_id,
                "status": readback.status,
                "source_sha": readback.source_sha,
                "log_path": str(readback.log_path),
                "queue_path": str(readback.queue_path),
                "proof_path": str(readback.proof_path),
                "log_sha256": readback.log_sha256,
                "queue_sha256": readback.queue_sha256,
                "external_action_authorized": False,
            },
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="APEX evidence-led audit runner")
    parser.add_argument(
        "--full-audit",
        action="store_true",
        help="Compatibility flag; full audit is the only mode",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Deprecated compatibility flag; does not authorize actions",
    )
    parser.add_argument(
        "--verify-run",
        metavar="RUN_ID",
        help="Verify one exact persisted run without executing a new audit",
    )
    args = parser.parse_args(argv)

    try:
        if args.verify_run:
            readback = verify_run_receipt(args.verify_run)
            _print_readback(readback)
            return 0

        run_id = _default_run_id()
        run, readback = execute_audit(
            run_id=run_id,
            source_sha=os.environ.get("GITHUB_SHA") or None,
            workflow_run_id=os.environ.get("GITHUB_RUN_ID") or None,
        )
        _print_readback(readback)
        if run.p0_count:
            print(f"P0 findings: {run.p0_count}", file=sys.stderr)
            return 1
        return 0
    except (AuditInvariantError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"APEX audit invariant failure: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
