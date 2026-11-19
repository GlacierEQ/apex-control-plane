"""Owner-local startup CLI must recover mission policy from private profile on every run."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import importlib.util
import json
import os


def entrypoint():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_owned_continuity.py"
    spec = importlib.util.spec_from_file_location("run_owned_continuity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfileTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "mission-profile.json"
        self.policy = {
            "schema": "glaciereq.owned-mission-profile/1",
            "mission_id": "mission-A", "store": "/root/local/store",
            "spiral_root": "/root/local/spiral", "bridge": "/root/local/bridge.py",
            "cloud_store": "/root/local/corpus", "cloud_index_db": "/root/local/index.db",
            "checkpoint_db": "/root/local/checkpoints.db",
            "namespace": "architecture", "source_ids": ["drive:primary:id-A"],
            "expected_cursor": "continue:exact", "required_corrections": ["CONTEXT FIRST"],
            "required_fact_keys": ["owner"]
        }
        self.path.write_text(json.dumps(self.policy))
        self.path.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_private_profile_is_readable_and_supplies_exact_cursor(self):
        loaded = entrypoint().load_profile(self.path)
        self.assertEqual(loaded["expected_cursor"], "continue:exact")
        self.assertEqual(loaded["source_ids"], ["drive:primary:id-A"])

    def test_world_readable_profile_is_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            entrypoint().load_profile(self.path)

    def test_duplicate_json_key_rejected(self):
        self.path.write_text('{"schema":"glaciereq.owned-mission-profile/1","schema":"fake"}')
        with self.assertRaises(ValueError):
            entrypoint().load_profile(self.path)

    def test_profile_symlink_refused(self):
        link = self.path.with_name("link.json")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            entrypoint().load_profile(link)

    def test_missing_source_policy_refused(self):
        self.policy["source_ids"] = []
        self.path.write_text(json.dumps(self.policy))
        with self.assertRaises(ValueError):
            entrypoint().load_profile(self.path)

    def test_owned_run_forwards_exact_policy_without_mutation(self):
        module = entrypoint()
        with mock.patch.object(module, "run_owned_cloud_mission", return_value={"status": "CHECKPOINTED"}) as run:
            result = module.run_profile(self.path, session_id="fresh-2", invocation_id="turn-3")
        self.assertEqual(result["status"], "CHECKPOINTED")
        args = run.call_args.kwargs
        self.assertEqual(args["session_id"], "fresh-2")
        self.assertEqual(args["expected_cursor"], "continue:exact")
        self.assertEqual(args["mission_id"], "mission-A")
        self.assertEqual(args["source_ids"], ["drive:primary:id-A"])


class ReadbackTests(ProfileTests):
    def test_missing_checkpoint_never_creates_database(self):
        module = entrypoint()
        with self.assertRaises(ValueError):
            module.read_checkpoint(self.path, session_id="session-2", invocation_id="turn-3")

    def test_ambiguous_invocation_rejected_before_database_access(self):
        module = entrypoint()
        with self.assertRaises(ValueError):
            module.read_checkpoint(self.path, session_id="session:spoof", invocation_id="turn-3")

    def test_committed_receipt_readback_scoped_to_profile(self):
        module = entrypoint()
        from src.apex_session_gateway import ContinuationEnvelope, _envelope_digest
        from src.apex_session_gateway_store import GatewayCheckpointStore
        db = self.path.parent / "receipts.db"
        self.policy["checkpoint_db"] = str(db)
        self.path.write_text(json.dumps(self.policy))
        store = GatewayCheckpointStore(db, mission_id="mission-A")
        key = "mission-A:model:session-2:turn-3"
        self.assertTrue(store.reserve(key))
        envelope = ContinuationEnvelope(
            operation_key=key, chat_session_id="session-2", mission_id="mission-A",
            source_ref="spiral-journal:" + "a" * 64, cursor="continue:exact",
            corrections=("CONTEXT FIRST",), response_text="indexed",
            attributions=(), memory_proposals=(), digest="",
            response_author="assistant", memory_authority="SOURCE_CANDIDATE_ONLY",
        )
        from dataclasses import replace
        envelope = replace(envelope, digest=_envelope_digest(envelope))
        store.persist(envelope)
        result = module.read_checkpoint(self.path, session_id="session-2", invocation_id="turn-3")
        self.assertEqual(result["checkpoint_digest"], envelope.digest)
        self.assertEqual(result["corrections_applied"], ["CONTEXT FIRST"])
        self.assertIsNone(result["completed_action"])
        # A separate process can recover the authenticated completed action.
        completed = {"action": "index_cloud", "documents": 2,
                     "namespace": "architecture", "evidence_digest": "sha256:abc",
                     "source_ids": ["drive:primary:id-A", "box:owner:id-B"]}
        from dataclasses import replace
        updated = replace(envelope, response_text=json.dumps(completed), digest="")
        updated = replace(updated, digest=_envelope_digest(updated))
        second_key = "mission-A:model:session-2:turn-4"
        updated = replace(updated, operation_key=second_key, digest="")
        updated = replace(updated, digest=_envelope_digest(updated))
        self.assertTrue(store.reserve(second_key))
        store.persist(updated)
        recovered = module.read_checkpoint(self.path, session_id="session-2", invocation_id="turn-4")
        self.assertEqual(recovered["completed_action"], completed)
        self.assertIsNone(result["completed_action"])
        self.assertFalse(result["native_chatgpt_startup_verified"])
        with self.assertRaises(Exception):
            module.read_checkpoint(self.path, session_id="session-2", invocation_id="other")

class ResumeDecisionTests(ProfileTests):
    def test_completed_action_changes_next_decision_without_rerunning(self):
        module = entrypoint()
        receipt = {"checkpoint_digest": "sha256:receipt", "journal_source_ref": "spiral-journal:head",
                   "cursor": "continue:exact", "completed_action": {
                       "action": "index_cloud", "documents": 1, "namespace": "architecture",
                       "source_ids": ["drive:primary:id-A"], "evidence_digest": "digest"}}
        with mock.patch.object(module, "read_checkpoint", return_value=receipt), \
             mock.patch.object(module, "run_owned_cloud_mission") as execute:
            result = module.decide_next_action(self.path, session_id="prior", invocation_id="done")
        self.assertEqual(result["decision"], "DO_NOT_REPEAT_COMPLETED_INDEX")
        execute.assert_not_called()

    def test_policy_drift_blocks_recovered_completion(self):
        module = entrypoint()
        receipt = {"checkpoint_digest": "sha256:receipt", "journal_source_ref": "spiral-journal:head",
                   "cursor": "continue:stale", "completed_action": {
                       "action": "index_cloud", "documents": 1, "namespace": "architecture",
                       "source_ids": ["drive:primary:id-A"], "evidence_digest": "digest"}}
        with mock.patch.object(module, "read_checkpoint", return_value=receipt):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                module.decide_next_action(self.path, session_id="prior", invocation_id="done")

    def test_missing_completed_action_never_claims_success(self):
        module = entrypoint()
        with mock.patch.object(module, "read_checkpoint", return_value={"completed_action": None}):
            with self.assertRaisesRegex(ValueError, "does not prove"):
                module.decide_next_action(self.path, session_id="prior", invocation_id="done")

class StartupRecoveryTests(ProfileTests):
    def test_prior_completion_changes_real_run_path_without_index(self):
        module = entrypoint()
        decision = {"decision": "DO_NOT_REPEAT_COMPLETED_INDEX", "checkpoint_digest": "proof"}
        with mock.patch.object(module, "decide_next_action", return_value=decision) as recover, mock.patch.object(module, "run_owned_cloud_mission") as index:
            result = module.run_profile(self.path, session_id="new-session", invocation_id="new-turn", previous_session_id="old-session", previous_invocation_id="old-turn")
        self.assertEqual(result["status"], "STARTUP_PRIOR_ACTION_APPLIED")
        self.assertFalse(result["index_executed"])
        recover.assert_called_once()
        index.assert_not_called()

    def test_conflicting_prior_completion_fails_before_index(self):
        module = entrypoint()
        with mock.patch.object(module, "decide_next_action", side_effect=ValueError("policy drift")), mock.patch.object(module, "run_owned_cloud_mission") as index:
            with self.assertRaisesRegex(ValueError, "policy drift"):
                module.run_profile(self.path, session_id="new", invocation_id="turn", previous_session_id="old", previous_invocation_id="old-turn")
        index.assert_not_called()

    def test_partial_prior_identity_refused_before_index(self):
        module = entrypoint()
        with mock.patch.object(module, "run_owned_cloud_mission") as index:
            with self.assertRaises(ValueError):
                module.run_profile(self.path, session_id="new", invocation_id="turn", previous_session_id="old")
        index.assert_not_called()
