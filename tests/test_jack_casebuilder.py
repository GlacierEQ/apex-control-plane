import unittest

from jack_casebuilder import (
    ActorNode,
    AllegationNode,
    DefenseNode,
    ElementMap,
    ElementState,
    FactNode,
    JackCaseGraph,
    PromotionState,
    ProofState,
    SourceRef,
)


class JackCasebuilderTests(unittest.TestCase):
    def test_occurrence_first_doe_actor_and_discovery(self):
        graph = JackCaseGraph("CASE-1")
        graph.add_source(SourceRef("SRC-1", "file:///source", 3))
        graph.add_actor(
            ActorNode(
                actor_id="DOE-1",
                canonical_name="Unknown detention actor",
                actor_class="security",
                organization="Entity",
                identity_status="doe",
                discovery_targets=("duty roster",),
            )
        )
        graph.add_event("EV-1", {"action": "detention", "location": "store"})
        graph.add_harm("H-1", {"type": "loss_of_liberty"})
        graph.add_fact(
            FactNode(
                fact_id="F-1",
                proposition="The subject was detained.",
                proof_state=ProofState.SUPPORTED,
                source_ids=("SRC-1",),
                event_ids=("EV-1",),
                actor_ids=("DOE-1",),
                harm_ids=("H-1",),
            )
        )
        graph.add_discovery_target(
            "D-1",
            {"record": "duty roster", "controlled_by": "Entity", "promotes": ["A-1"]},
        )
        allegation = AllegationNode(
            allegation_id="A-1",
            title="Detention",
            actor_ids=("DOE-1",),
            event_ids=("EV-1",),
            factual_predicate="The subject was detained by an unidentified security actor.",
            legal_theory="test theory",
            elements=(
                ElementMap(
                    "E-1",
                    "restraint",
                    ElementState.PROVEN,
                    fact_ids=("F-1",),
                    source_ids=("SRC-1",),
                ),
            ),
            source_ids=("SRC-1",),
            harm_ids=("H-1",),
            defenses=(DefenseNode("DEF-1", "reasonable detention"),),
            discovery_targets=("D-1",),
            promotion_state=PromotionState.HARDENED,
            proof_score=4,
            legal_score=4,
            causation_score=4,
            harm_score=3,
            defense_risk=2,
        )
        graph.add_allegation(allegation)
        graph.validate_promotions()
        self.assertEqual(graph.pressure_map()[0]["allegation_id"], "A-1")
        self.assertEqual(graph.receipt()["counts"]["allegations"], 1)

    def test_missing_element_blocks_promotion(self):
        allegation = AllegationNode(
            allegation_id="A-2",
            title="Blocked",
            actor_ids=("DOE-1",),
            event_ids=("EV-1",),
            factual_predicate="x",
            legal_theory="y",
            elements=(ElementMap("E-2", "intent", ElementState.MISSING, gap="knowledge evidence"),),
            source_ids=("SRC-1",),
            defenses=(DefenseNode("DEF-2", "mistake"),),
            promotion_state=PromotionState.PLEADING_READY,
        )
        self.assertIn("elements_missing_or_disputed", allegation.blockers())


if __name__ == "__main__":
    unittest.main()
