"""Regression: a correct paraphrase cannot stand in for performed mission work."""
import unittest
from src.mission_fidelity_admission import assess_mission_fidelity, FidelityViolation

class MissionFidelityTests(unittest.TestCase):
    def test_rejects_sample_for_full_historical_audit(self):
        with self.assertRaisesRegex(FidelityViolation, "coverage"):
            assess_mission_fidelity({"mission_id":"audit-1","required_lanes":["historical_turns","all_matters","counterexamples","denominator"],"correction_ids":["C-1"],"cursor":"v7"}, {"mission_id":"audit-1","applied_correction_ids":["C-1"],"cursor":"v7","completed_lanes":["historical_turns"],"evidence_refs":["github:1"],"claimed_complete":True})
    def test_rejects_unapplied_correction(self):
        with self.assertRaisesRegex(FidelityViolation, "correction"):
            assess_mission_fidelity({"mission_id":"audit-1","required_lanes":["historical_turns"],"correction_ids":["C-1"],"cursor":"v7"}, {"mission_id":"audit-1","applied_correction_ids":[],"cursor":"v7","completed_lanes":["historical_turns"],"evidence_refs":["github:1"],"claimed_complete":True})
    def test_rejects_wrong_cursor(self):
        with self.assertRaisesRegex(FidelityViolation, "cursor"):
            assess_mission_fidelity({"mission_id":"audit-1","required_lanes":["historical_turns"],"correction_ids":[],"cursor":"v7"}, {"mission_id":"audit-1","applied_correction_ids":[],"cursor":"v6","completed_lanes":["historical_turns"],"evidence_refs":["github:1"],"claimed_complete":True})
    def test_partial_progress_is_not_completion(self):
        result=assess_mission_fidelity({"mission_id":"audit-1","required_lanes":["historical_turns","all_matters"],"correction_ids":[],"cursor":"v7"}, {"mission_id":"audit-1","applied_correction_ids":[],"cursor":"v7","completed_lanes":["historical_turns"],"evidence_refs":["github:1"],"claimed_complete":False})
        self.assertEqual(result["status"],"PARTIAL")
        self.assertEqual(result["remaining_lanes"],["all_matters"])
    def test_full_verified_scope(self):
        result=assess_mission_fidelity({"mission_id":"audit-1","required_lanes":["historical_turns"],"correction_ids":["C-1"],"cursor":"v7"}, {"mission_id":"audit-1","applied_correction_ids":["C-1"],"cursor":"v7","completed_lanes":["historical_turns"],"evidence_refs":["github:1"],"claimed_complete":True})
        self.assertEqual(result["status"],"COMPLETE")
    def test_rejects_no_evidence(self):
        with self.assertRaisesRegex(FidelityViolation, "evidence"):
            assess_mission_fidelity({"mission_id":"audit-1","required_lanes":["historical_turns"],"correction_ids":[],"cursor":"v7"}, {"mission_id":"audit-1","applied_correction_ids":[],"cursor":"v7","completed_lanes":["historical_turns"],"evidence_refs":[],"claimed_complete":True})
if __name__=="__main__": unittest.main()
