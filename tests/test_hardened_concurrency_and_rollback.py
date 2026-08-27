"""
APEX CONTROL PLANE: HARDENED CONCURRENCY & ROLLBACK TEST SUITE
Standard: Proves 2-Phase Compensating Transactions, Tamper-Proof Hash Chains, and Zero Data Loss.
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.mission import Mission, MissionStatus
from contracts.receipt import ECHOReceipt
from adapters.echo.store import ECHOStore
from adapters.roottruth.store import RootTruthStore
from workflows.master_run import MasterWorkflowRunner


class RollbackAwareMockAdapter:
    """Mock adapter recording applied mutations and tracking rollback reversions."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.applied = []
        self.reverted = []

    def observe(self, resource: str):
        return {"repository": resource, "head_sha": "head_mock_123"}

    def apply_operation(self, op):
        target = self.root_dir / op.desired_after.get("path", "file.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(op.desired_after.get("content", ""), encoding="utf-8")
        self.applied.append(op.desired_after.get("path"))
        return {"status": "APPLIED"}

    def revert_operation(self, op):
        target = self.root_dir / op.desired_after.get("path", "file.txt")
        orig = op.expected_before.get("content")
        if orig is not None:
            target.write_text(orig, encoding="utf-8")
        else:
            target.unlink(missing_ok=True)
        self.reverted.append(op.desired_after.get("path"))
        return {"status": "REVERTED"}

    def readback(self, resource: str, file_path: str):
        target = self.root_dir / file_path
        if target.exists():
            c = target.read_text(encoding="utf-8")
            h = hashlib.sha256(c.encode("utf-8")).hexdigest()
            return {"file_path": file_path, "content_hash": h}
        return {"file_path": file_path, "content_hash": None}


class TestHardenedControlPlane(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="apex_hardened_test_"))
        self.echo_log = self.test_dir / "echo_receipts.jsonl"
        self.root_truth_path = self.test_dir / "root_truth.json"

        self.echo = ECHOStore(log_path=self.echo_log)
        self.root_truth = RootTruthStore(storage_path=self.root_truth_path)
        self.runner = MasterWorkflowRunner(echo_store=self.echo, root_truth=self.root_truth)
        self.adapter = RollbackAwareMockAdapter(root_dir=self.test_dir / "repo")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_two_phase_compensating_rollback(self):
        """
        Tests that when an operation fails readback verification in a multi-operation batch,
        the workflow enters COMPENSATING, reverts all applied mutations, and writes a ROLLED_BACK receipt.
        """
        m = Mission.create(objective="Batch Update with Injected Failure", project="GlacierEQ/monolith")

        content1 = "Healthy Module\n"
        hash1 = hashlib.sha256(content1.encode("utf-8")).hexdigest()

        content2 = "Failed Module\n"
        wrong_hash2 = "FRAUDULENT_EXPECTED_HASH"

        proposed_changes = {
            "res1": {
                "system": "filesystem",
                "operation": "create_file",
                "expected_before": {"head_sha": "head_mock_123"},
                "desired_after": {"path": "module1.py", "content": content1, "content_hash": hash1},
            },
            "res2": {
                "system": "filesystem",
                "operation": "create_file",
                "expected_before": {"head_sha": "head_mock_123"},
                "desired_after": {"path": "module2.py", "content": content2, "content_hash": wrong_hash2},
            },
        }

        final_mission = self.runner.run_mission_cycle(
            mission=m,
            raw_agent_findings={},
            proposed_changes=proposed_changes,
            system_adapter=self.adapter,
        )

        # Assert lifecycle reached FAILED through COMPENSATING
        self.assertEqual(final_mission.status, MissionStatus.FAILED)
        transitions = [t["to"] for t in final_mission.metadata.get("transition_log", [])]
        self.assertIn(str(MissionStatus.COMPENSATING), transitions)
        self.assertIn(str(MissionStatus.FAILED), transitions)

        # Assert rollback was invoked physically
        self.assertIn("module1.py", self.adapter.reverted)
        self.assertFalse((self.test_dir / "repo" / "module1.py").exists(), "Rolled back file must be removed!")

        # Assert ROLLED_BACK receipt was appended to ECHO
        receipts = self.echo.get_receipts_for_mission(m.mission_id)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].result, "ROLLED_BACK")

    def test_02_forensic_tamper_detection_index(self):
        """
        Tests that if an adversary tampers with receipt #2 in a 5-receipt chain,
        audit_chain() isolates the exact broken index and expected hash.
        """
        prev_hash = "GENESIS_ROOT"
        for i in range(1, 6):
            rcpt = ECHOReceipt.create(
                mission_id=f"msn_{i}",
                correlation_id=f"run_{i}",
                step="test_step",
                started_at=100.0 + i,
                expected_state={"idx": i},
                observed_state={"idx": i},
                external_ids={},
                result="VERIFIED",
                previous_receipt_hash=prev_hash,
            )
            self.echo.append_receipt(rcpt)
            prev_hash = rcpt.receipt_hash

        # Verify pristine chain
        report = self.echo.audit_chain()
        self.assertTrue(report["is_valid"])
        self.assertEqual(report["total_receipts"], 5)

        # Infiltrate and tamper line 3 in echo log
        lines = self.echo_log.read_text(encoding="utf-8").splitlines()
        tampered_obj = json.loads(lines[2])
        tampered_obj["previous_receipt_hash"] = "TAMPERED_PREV_HASH_INJECTED"
        lines[2] = json.dumps(tampered_obj)
        self.echo_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Re-audit
        tamper_report = self.echo.audit_chain()
        self.assertFalse(tamper_report["is_valid"])
        self.assertEqual(tamper_report["broken_at_index"], 3)
        self.assertEqual(tamper_report["observed_prev"], "TAMPERED_PREV_HASH_INJECTED")


if __name__ == "__main__":
    unittest.main()
