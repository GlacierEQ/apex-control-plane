#!/usr/bin/env python3
"""
APEX CONTROL PLANE COMMAND LINE INTERFACE (CLI)
Standard: Master Control Console for Mission Management, ECHO Auditing, and RootTruth Inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.mission import Mission, MissionStatus
from adapters.echo.store import ECHOStore
from adapters.roottruth.store import RootTruthStore
from workflows.master_run import MasterWorkflowRunner


class MockCliAdapter:
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir

    def observe(self, resource: str):
        return {"repository": resource, "head_sha": "head_sha_cli_001"}

    def apply_operation(self, op):
        p = self.target_dir / op.desired_after.get("path", "file.txt")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(op.desired_after.get("content", ""), encoding="utf-8")
        return {"status": "APPLIED"}

    def readback(self, resource: str, file_path: str):
        p = self.target_dir / file_path
        if p.exists():
            c = p.read_text(encoding="utf-8")
            h = hashlib.sha256(c.encode("utf-8")).hexdigest()
            return {"file_path": file_path, "content_hash": h}
        return {"file_path": file_path, "content_hash": None}

    def revert_operation(self, op):
        p = self.target_dir / op.desired_after.get("path", "file.txt")
        p.unlink(missing_ok=True)
        return {"status": "REVERTED"}


def cmd_audit(args):
    echo = ECHOStore()
    report = echo.audit_chain()
    print("=" * 70)
    print("🔍 APEX ECHO RECEIPT LEDGER: FORENSIC HASH CHAIN AUDIT")
    print("=" * 70)
    print(f"Chain Status       : {'🟢 100% PRISTINE & VALID' if report.get('is_valid') else '❌ TAMPER DETECTED'}")
    print(f"Total Receipts     : {report.get('total_receipts', 0)}")
    if report.get("head_receipt_hash"):
        print(f"Head Receipt Hash  : {report.get('head_receipt_hash')}")
    if not report.get("is_valid"):
        print(f"Broken at Index    : {report.get('broken_at_index')}")
        print(f"Expected Previous  : {report.get('expected_prev')}")
        print(f"Observed Previous  : {report.get('observed_prev')}")
    print("=" * 70)
    return 0 if report.get("is_valid") else 1


def cmd_truth(args):
    rt = RootTruthStore()
    truths = rt.all_truths()
    print("=" * 70)
    print("🏛️ APEX ROOTTRUTH STORE: AUTHORITATIVE STATE PROJECTION")
    print("=" * 70)
    if not truths:
        print("No entities currently tracked in RootTruthStore.")
    for k, v in sorted(truths.items()):
        print(f"• {k}")
        print(f"    Value     : {v.get('value')}")
        print(f"    Receipt ID: {v.get('provenance_receipt_id')}")
        print(f"    Updated   : {v.get('version')}")
    print("=" * 70)
    return 0


def cmd_create(args):
    m = Mission.create(
        objective=args.objective,
        project=args.project,
        priority=args.priority,
        repositories=[args.repo] if args.repo else [],
    )
    print("=" * 70)
    print(f"🚀 APEX MISSION CREATED: {m.mission_id}")
    print("=" * 70)
    print(f"Objective     : {m.objective}")
    print(f"Project       : {m.project}")
    print(f"Priority      : {m.priority}")
    print(f"Correlation ID: {m.correlation_id}")
    print(f"Initial Status: {m.status.value}")
    print("=" * 70)
    return 0


def cmd_run_sample(args):
    print("=" * 70)
    print("⚡ APEX CONTROL PLANE: EXECUTING FULL LIFECYCLE MISSION")
    print("=" * 70)
    m = Mission.create(
        objective=args.objective or "Demonstrate Full 15-State Control Loop",
        project="GlacierEQ/monolith",
        priority="P0",
    )
    temp_dir = Path("/tmp/apex_sample_run")
    temp_dir.mkdir(parents=True, exist_ok=True)
    adapter = MockCliAdapter(temp_dir)

    content = f"APEX Sovereign State Commit\nMission: {m.mission_id}\n"
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()

    changes = {
        "GlacierEQ/monolith": {
            "system": "filesystem",
            "operation": "create_file",
            "expected_before": {"head_sha": "head_sha_cli_001"},
            "desired_after": {"path": "state.txt", "content": content, "content_hash": h},
        }
    }

    runner = MasterWorkflowRunner()
    result_mission = runner.run_mission_cycle(
        mission=m,
        raw_agent_findings={},
        proposed_changes=changes,
        system_adapter=adapter,
    )

    print(f"Final Mission Status: {result_mission.status.value}")
    print("Transition Log:")
    for t in result_mission.metadata.get("transition_log", []):
        print(f"  [{t.get('from')}] ➔ [{t.get('to')}]: {t.get('reason')}")
    print("=" * 70)
    return 0


def main():
    parser = argparse.ArgumentParser(description="APEX Control Plane Master CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # audit
    subparsers.add_parser("audit", help="Run cryptographic audit on ECHO receipt ledger")

    # truth
    subparsers.add_parser("truth", help="Display all entities from RootTruthStore")

    # create
    p_create = subparsers.add_parser("create", help="Create a new typed Mission")
    p_create.add_argument("--objective", required=True, help="Mission objective")
    p_create.add_argument("--project", default="general", help="Project name")
    p_create.add_argument("--priority", default="P0", choices=["P0", "P1", "P2"], help="Priority")
    p_create.add_argument("--repo", help="Target repository")

    # run-sample
    p_run = subparsers.add_parser("run-sample", help="Run a sample mission through all 15 states")
    p_run.add_argument("--objective", help="Optional mission objective")

    args = parser.parse_args()

    if args.command == "audit":
        sys.exit(cmd_audit(args))
    elif args.command == "truth":
        sys.exit(cmd_truth(args))
    elif args.command == "create":
        sys.exit(cmd_create(args))
    elif args.command == "run-sample":
        sys.exit(cmd_run_sample(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
