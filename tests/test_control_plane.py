"""
APEX CONTROL PLANE: L2 EPISTEMIC VERIFICATION TEST SUITE
Standard: Full verification of Mission State Machine, ContextPack, ChangeSets, Readback Verifier, and ECHO Hash Chains.
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

from contracts.changeset import ChangeSet, Operation
from contracts.context_pack import ContextPack
from contracts.mission import Mission, MissionStatus
from contracts.receipt import ECHOReceipt
from adapters.echo.store import ECHOStore
from adapters.roottruth.store import RootTruthStore
from verification.state_diff import StateVerifier
from workflows.master_run import MasterWorkflowRunner


class MockSystemAdapter:
    """Mock adapter for GitHub / Filesystem mutations."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.head_sha = "mock_sha_123"

    def observe(self, resource: str):
        return {"repository": resource, "head_sha": self.head_sha}

    def apply_operation(self, op: Operation):
        target = self.root_dir / op.desired_after.get("path", "file.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(op.desired_after.get("content", ""), encoding="utf-8")
        return {"status": "APPLIED"}

    def readback(self, resource: str, file_path: str):
        target = self.root_dir / file_path
        if target.exists():
            c = target.read_text(encoding="utf-8")
            h = hashlib.sha256(c.encode("utf-8")).hexdigest()
            return {"file_path": file_path, "content_hash": h}
        return {"file_path": file_path, "content_hash": None}


class TestApexControlPlane(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="apex_cp_test_"))
        self.echo_log = self.test_dir / "echo_receipts.jsonl"
        self.root_truth_path = self.test_dir / "root_truth.json"

        self.echo = ECHOStore(log_path=self.echo_log)
        self.root_truth = RootTruthStore(storage_path=self.root_truth_path)
        self.runner = MasterWorkflowRunner(echo_store=self.echo, root_truth=self.root_truth)
        self.adapter = MockSystemAdapter(root_dir=self.test_dir / "repo")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_mission_state_machine_laws(self):
        m = Mission.create(objective="Upgrade repo X", project="job-app-master")
        self.assertEqual(m.status, MissionStatus.RECEIVED)

        m.transition_to(MissionStatus.CONTEXT_HYDRATING)
        self.assertEqual(m.status, MissionStatus.CONTEXT_HYDRATING)

        m.transition_to(MissionStatus.COMPLETE)
        self.assertEqual(m.status, MissionStatus.COMPLETE)

        # Cannot transition out of COMPLETE without RETRYING
        with self.assertRaises(ValueError):
            m.transition_to(MissionStatus.EXECUTING)

    def test_02_context_pack_lock(self):
        cp = ContextPack.create("msn_1", "run_1")
        cp.add_fact("Repo exists", "github", verified=True)
        self.assertFalse(cp.is_locked)

        cp.lock()
        self.assertTrue(cp.is_locked)

        with self.assertRaises(ValueError):
            cp.add_fact("Another fact", "github")

    def test_03_echo_hash_chain_integrity(self):
        r1 = ECHOReceipt.create(
            mission_id="msn_1",
            correlation_id="run_1",
            step="step1",
            started_at=100.0,
            expected_state={"a": 1},
            observed_state={"a": 1},
            external_ids={},
            result="VERIFIED",
            previous_receipt_hash="GENESIS_ROOT",
        )
        self.echo.append_receipt(r1)

        r2 = ECHOReceipt.create(
            mission_id="msn_1",
            correlation_id="run_1",
            step="step2",
            started_at=105.0,
            expected_state={"b": 2},
            observed_state={"b": 2},
            external_ids={},
            result="VERIFIED",
            previous_receipt_hash=r1.receipt_hash,
        )
        self.echo.append_receipt(r2)

        self.assertTrue(self.echo.verify_chain_integrity())

        # Assert broken link raises ValueError
        r_broken = ECHOReceipt.create(
            mission_id="msn_1",
            correlation_id="run_1",
            step="step3",
            started_at=110.0,
            expected_state={"c": 3},
            observed_state={"c": 3},
            external_ids={},
            result="VERIFIED",
            previous_receipt_hash="FRAUDULENT_HASH",
        )
        with self.assertRaises(ValueError):
            self.echo.append_receipt(r_broken)

    def test_04_full_master_lifecycle_end_to_end_success(self):
        m = Mission.create(objective="Refactor Auth", project="GlacierEQ/job-app")
        content = "print('Auth Hardened')\n"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        proposed_changes = {
            "GlacierEQ/job-app": {
                "system": "github",
                "operation": "create_file",
                "expected_before": {"head_sha": "mock_sha_123"},
                "desired_after": {
                    "path": "src/auth.py",
                    "content": content,
                    "content_hash": content_hash,
                },
            }
        }

        # Run workflow
        final_mission = self.runner.run_mission_cycle(
            mission=m,
            raw_agent_findings={},
            proposed_changes=proposed_changes,
            system_adapter=self.adapter,
        )

        # Invariant: Must reach COMPLETE because readback matches expected!
        self.assertEqual(final_mission.status, MissionStatus.COMPLETE)

        # Verify receipt was appended
        receipts = self.echo.get_receipts_for_mission(m.mission_id)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].result, "VERIFIED")

        # Verify RootTruth was updated
        truth = self.root_truth.get("github:GlacierEQ/job-app")
        self.assertEqual(truth["status"], "UPDATED")

    def test_05_readback_mismatch_blocks_complete(self):
        m = Mission.create(objective="Refactor Auth", project="GlacierEQ/job-app")
        content = "print('Auth Hardened')\n"
        wrong_hash = "wrong_hash_12345"

        proposed_changes = {
            "GlacierEQ/job-app": {
                "system": "github",
                "operation": "create_file",
                "expected_before": {"head_sha": "mock_sha_123"},
                "desired_after": {
                    "path": "src/auth.py",
                    "content": content,
                    "content_hash": wrong_hash,  # Intentional mismatch!
                },
            }
        }

        final_mission = self.runner.run_mission_cycle(
            mission=m,
            raw_agent_findings={},
            proposed_changes=proposed_changes,
            system_adapter=self.adapter,
        )

        # Invariant: EXECUTING != COMPLETE, MUTATING != COMPLETE!
        # Because observed delta != expected delta, it MUST transition to FAILED!
        self.assertEqual(final_mission.status, MissionStatus.FAILED)
        self.assertIn("Verification failed", final_mission.metadata["transition_log"][-1]["reason"])


if __name__ == "__main__":
    unittest.main()
