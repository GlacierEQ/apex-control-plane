"""VICE pursuit: advance evidence-backed action without adopting imaginary defenses."""
import unittest
from dataclasses import replace
from src.pursuit_engine import (
    PursuitFinding, Counterclaim, PursuitHistory, PursuitStage,
    next_pursuit_step, pursuit_impact_candidate, dispatch_pursuit_step, PursuitViolation,
)
from src.connector_mission_router import ConnectorCapability, MissionAdmission, AdmissionDenied


def finding(**changes):
    base = PursuitFinding(
        mission_id='test-case-A', finding_id='FINDING-01', actor_id='reviewer-A',
        observation='recorded session lasted 12 seconds',
        observation_ref='test-viewer:event-123', observation_sha256='a' * 64,
        observation_authenticated=True, duty_id='TEST-PROCEDURE',
        duty_ref='policy:sample-1', duty_verified=True,
        target='documented lawful disposition',
    )
    return replace(base, **changes)


class PursuitTests(unittest.TestCase):
    def test_initial_challenge_uses_sourced_fact_and_duty(self):
        step = next_pursuit_step(finding(), PursuitHistory())
        self.assertEqual(step.stage, PursuitStage.REQUEST_ACCOUNT)
        self.assertIn('test-viewer:event-123', step.evidence_refs)
        self.assertEqual(step.actor_id, 'reviewer-A')
        self.assertFalse(step.outcome_verified)

    def test_unsubstantiated_print_story_cannot_erase_short_session(self):
        f = finding(counterclaims=(Counterclaim('later printed', 'reviewer-A'),))
        step = next_pursuit_step(f, PursuitHistory())
        self.assertEqual(step.stage, PursuitStage.REQUEST_ACCOUNT)
        self.assertEqual(step.adverse_claims_pending, ('later printed',))
        self.assertIn('12 seconds', step.position)

    def test_substantiated_counterclaim_requires_targeted_reassessment(self):
        f = finding(counterclaims=(Counterclaim('later printed', 'reviewer-A',
            supporting_refs=('print:job-1',), independently_verified=True),))
        step = next_pursuit_step(f, PursuitHistory())
        self.assertEqual(step.stage, PursuitStage.REASSESS)
        self.assertIn('print:job-1', step.evidence_refs)
        self.assertIn('12 seconds', step.position)

    def test_another_actor_counterclaim_does_not_count_as_this_actors_review(self):
        f = finding(counterclaims=(Counterclaim('another agent reviewed', 'reviewer-B',
            supporting_refs=('agency:other-review',), independently_verified=True),))
        self.assertEqual(next_pursuit_step(f, PursuitHistory()).stage, PursuitStage.REQUEST_ACCOUNT)

    def test_missing_source_routes_to_authentication_not_an_accusation(self):
        f = finding(observation_authenticated=False)
        self.assertEqual(next_pursuit_step(f, PursuitHistory()).stage, PursuitStage.AUTHENTICATE)

    def test_unsourced_observation_does_not_claim_authentication(self):
        step = next_pursuit_step(finding(observation_authenticated=False), PursuitHistory())
        self.assertNotIn('Authenticated observation:', step.position)

    def test_missing_duty_or_actor_moves_to_specific_acquisition(self):
        self.assertEqual(next_pursuit_step(finding(duty_verified=False), PursuitHistory()).stage, PursuitStage.ESTABLISH_DUTY)
        self.assertEqual(next_pursuit_step(finding(actor_id=''), PursuitHistory()).stage, PursuitStage.IDENTIFY_ACTOR)

    def test_after_challenge_unanswered_independent_route_escalates(self):
        h = PursuitHistory(challenge_receipt='gmail:native-sent-id', response_window_elapsed=True,
                           response_window_source='policy:deadline',
                           escalation_route='review:independent-office', escalation_authorized=True)
        step = next_pursuit_step(finding(), h)
        self.assertEqual(step.stage, PursuitStage.INDEPENDENT_REVIEW)
        self.assertFalse(step.outcome_verified)
        self.assertIn('gmail:native-sent-id', step.evidence_refs)

    def test_no_route_does_not_invent_escalation_or_finish(self):
        h = PursuitHistory(challenge_receipt='gmail:native-sent-id', response_window_elapsed=True,
                           response_window_source='policy:due')
        self.assertEqual(next_pursuit_step(finding(), h).stage, PursuitStage.FIND_LAWFUL_ROUTE)

    def test_unverified_elapsed_time_does_not_trigger_escalation(self):
        h = PursuitHistory(challenge_receipt='gmail:sent', response_window_elapsed=True,
                           escalation_route='review:independent-office', escalation_authorized=True)
        self.assertEqual(next_pursuit_step(finding(), h).stage, PursuitStage.VERIFY_DISPOSITION)

    def test_agency_ack_does_not_complete_target(self):
        h = PursuitHistory(challenge_receipt='gmail:sent', agency_ack='gmail:ack')
        step = next_pursuit_step(finding(), h)
        self.assertEqual(step.stage, PursuitStage.VERIFY_DISPOSITION)
        self.assertFalse(step.outcome_verified)

    def test_closure_requires_native_outcome_plus_independent_readback(self):
        h = PursuitHistory(target_result_ref='agency:order', target_result_readback='agency:confirmed', target_result_verified=True)
        step = next_pursuit_step(finding(), h)
        self.assertEqual(step.stage, PursuitStage.COMPLETE)
        self.assertTrue(step.outcome_verified)
        with self.assertRaises(PursuitViolation):
            next_pursuit_step(finding(), replace(h, target_result_readback=''))

    def test_outbound_uses_existing_context_reservation_readback_and_handoff_gate(self):
        step = next_pursuit_step(finding(), PursuitHistory())
        admitted = MissionAdmission('test-case-A','test-case-A',True,'cursor-1',())
        cap = ConnectorCapability('gmail','send',True,True,True)
        used = []
        out = dispatch_pursuit_step(step, admission=admitted, capability=cap,
            reserve=lambda key: used.append(key) or True,
            execute=lambda: {'native_id':'sent-1'},
            readback=lambda result: result['native_id']=='sent-1',
            persist_continuation=lambda receipt: receipt,
            verify_continuation=lambda record: record.native_result['native_id']=='sent-1')
        self.assertEqual(out['native_id'],'sent-1')
        self.assertEqual(len(used),1)
        with self.assertRaises(PursuitViolation):
            dispatch_pursuit_step(step, admission=replace(admitted, expected_mission_id='OTHER'), capability=cap,
                reserve=lambda x: True, execute=lambda: None, readback=lambda r: True,
                persist_continuation=lambda r:r, verify_continuation=lambda r:True)

    def test_pursuit_step_becomes_source_bound_apex_impact_candidate(self):
        from src.continuous_impact_selection import ImpactCandidate
        step = next_pursuit_step(finding(), PursuitHistory())
        candidate = pursuit_impact_candidate(step)
        self.assertIsInstance(candidate, ImpactCandidate)
        self.assertEqual(candidate.operation_class, 'CASE_EXECUTION')
        self.assertEqual(candidate.metadata['route_kind'], 'execution')
        self.assertEqual(candidate.metadata['actor_id'], 'reviewer-A')
        self.assertIn('test-viewer:event-123', candidate.evidence_refs)
        self.assertEqual(candidate.candidate_id, step.operation_id)
        with self.assertRaises(PursuitViolation):
            pursuit_impact_candidate(next_pursuit_step(
                finding(), PursuitHistory(target_result_ref='agency:order',
                target_result_readback='agency:confirmed', target_result_verified=True)))

    def test_independent_review_maps_to_escalation_not_prosecution(self):
        h = PursuitHistory(challenge_receipt='gmail:sent', response_window_elapsed=True,
                           response_window_source='policy:deadline',
                           escalation_route='review:independent-office', escalation_authorized=True)
        candidate = pursuit_impact_candidate(next_pursuit_step(finding(), h))
        self.assertEqual(candidate.metadata['route_kind'], 'escalation')
        self.assertNotEqual(candidate.metadata['route_kind'], 'prosecution')

    def test_new_source_changes_idempotency_key_but_same_source_does_not(self):
        first = next_pursuit_step(finding(), PursuitHistory())
        replay = next_pursuit_step(finding(), PursuitHistory())
        additional = next_pursuit_step(finding(
            observation_ref='test-viewer:event-456',
            observation_sha256='b' * 64), PursuitHistory())
        self.assertEqual(first.operation_id, replay.operation_id)
        self.assertNotEqual(first.operation_id, additional.operation_id)

    def test_unsourced_counterclaim_cannot_be_marked_evidence_backed(self):
        f = finding(counterclaims=(Counterclaim('printed later', 'reviewer-A',
            supporting_refs=('unsupported-plain-text',), independently_verified=True),))
        step = next_pursuit_step(f, PursuitHistory())
        self.assertEqual(step.stage, PursuitStage.REQUEST_ACCOUNT)
        self.assertEqual(step.adverse_claims_pending, ('printed later',))

    def test_derived_summary_cannot_mark_target_complete(self):
        h = PursuitHistory(target_result_ref='summary:finished',
            target_result_readback='summary:claimed', target_result_verified=True)
        with self.assertRaises(PursuitViolation):
            next_pursuit_step(finding(), h)

    def test_escalation_receipt_transitions_to_tracking_not_repeat_escalation(self):
        h = PursuitHistory(challenge_receipt='gmail:sent', response_window_elapsed=True,
            response_window_source='policy:elapsed', escalation_route='review:independent-office',
            escalation_authorized=True, independent_review_receipt='review:accepted-intake')
        step = next_pursuit_step(finding(), h)
        self.assertEqual(step.stage, PursuitStage.VERIFY_DISPOSITION)
        self.assertIn('review:accepted-intake', step.evidence_refs)
        self.assertFalse(step.outcome_verified)

    def test_no_unauthorized_effect_from_unverified_or_complete_step(self):
        step = next_pursuit_step(finding(observation_authenticated=False), PursuitHistory())
        admission = MissionAdmission('test-case-A','test-case-A',True,'cursor-1',())
        cap = ConnectorCapability('gmail','send',True,True,True)
        with self.assertRaises(PursuitViolation):
            dispatch_pursuit_step(step, admission=admission, capability=cap, reserve=lambda k:True,
                execute=lambda:None, readback=lambda r:True,
                persist_continuation=lambda r:r, verify_continuation=lambda r:True)


if __name__ == '__main__':
    unittest.main()
