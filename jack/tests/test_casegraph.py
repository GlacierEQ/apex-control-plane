from jack.src.casebuilder import (
    Allegation,
    Contradiction,
    DiscoveryTarget,
    ElementSupport,
    Lane,
    ProofState,
    PromotionState,
    SourceRef,
)
from jack.src.casegraph import (
    AccountabilityPath,
    ActorNode,
    AllegationLink,
    CaseGraph,
    ContradictionAssessment,
    ContradictionState,
    DamageRecord,
    DefenseTheory,
    EventNode,
    FactProposition,
    RemedyPath,
    compile_case_graph,
)


def _source(source_id: str) -> SourceRef:
    return SourceRef(source_id, "record", f"source:{source_id}", ProofState.VERIFIED_PRIMARY)


def _allegation(**overrides) -> Allegation:
    values = dict(
        id="ALG-1",
        title="Detention without established authority",
        lane=Lane.CIVIL,
        actor_ids=["ACT-DOE-1"],
        event_ids=["EVT-1"],
        act="Controlled departure during the event.",
        factual_theory="The actor exercised control over movement.",
        legal_theory="Unlawful restraint theory.",
        elements=[ElementSupport("restraint", ("SRC-1",), (), (), True)],
        primary_source_ids=["SRC-1"],
        corroborating_source_ids=["SRC-2"],
        causation="The restraint caused a loss of liberty.",
        harm_ids=["DMG-1"],
        defenses=["lawful authority"],
        rebuttals=["FACT-2 contradicts the asserted authority basis"],
        discovery_target_ids=[],
        remedy_ids=["REM-1"],
        proof_state=ProofState.CORROBORATED,
    )
    values.update(overrides)
    return Allegation(**values)


def _complete_graph(*, accountability_ready=True) -> CaseGraph:
    graph = CaseGraph("MATTER-1")
    graph.add_source(_source("SRC-1"))
    graph.add_source(_source("SRC-2"))
    graph.add_source(_source("SRC-3"))

    graph.add_actor(ActorNode("ACT-DOE-1", "Unknown initiating actor"))
    graph.add_fact(
        FactProposition(
            "FACT-1",
            "Actor controlled departure.",
            ("SRC-1", "SRC-2"),
            ("ACT-DOE-1",),
            ("EVT-1",),
        )
    )
    graph.add_fact(
        FactProposition(
            "FACT-2",
            "No authority record is presently linked.",
            ("SRC-3",),
            ("ACT-DOE-1",),
            ("EVT-1",),
            disputed=True,
        )
    )
    graph.add_damage(
        DamageRecord(
            "DMG-1",
            "Loss of liberty",
            ("EVT-1",),
            ("SRC-1",),
            category="LOSS_OF_LIBERTY",
        )
    )
    graph.add_event(
        EventNode(
            "EVT-1",
            "Initial restraint",
            "2026-08-14",
            "store exit",
            "Controlled departure",
            ("ACT-DOE-1",),
            ("FACT-1", "FACT-2"),
            ("SRC-1", "SRC-2"),
            ("DMG-1",),
        )
    )
    graph.add_remedy(
        RemedyPath(
            "REM-1",
            "civil",
            "Relief tied to the surviving theory",
            ("ALG-1",),
        )
    )
    graph.add_allegation(_allegation())
    graph.add_defense(
        DefenseTheory(
            "DEF-1",
            "ALG-1",
            "Lawful authority",
            supporting_fact_ids=("FACT-2",),
            rebuttal_fact_ids=("FACT-1",),
        )
    )
    graph.add_accountability_path(
        AccountabilityPath(
            "ACC-1",
            "ALG-1",
            "court",
            "civil claim",
            "surviving element-mapped theory",
            remedy_ids=("REM-1",),
            ready=accountability_ready,
        )
    )
    graph.link_allegation(
        AllegationLink(
            "ALG-1",
            fact_ids=("FACT-1", "FACT-2"),
            duty_or_prohibition=("restraint requires lawful authority",),
            defense_ids=("DEF-1",),
            accountability_path_ids=("ACC-1",),
        )
    )
    return graph


def test_full_graph_reaches_trial_ready_and_emits_ledgers():
    graph = _complete_graph()
    compiled = compile_case_graph(graph)
    assert compiled["promotion_report"]["ALG-1"] == PromotionState.TRIAL_READY.value
    assert compiled["metrics"]["trial_ready"] == 1
    assert len(compiled["ledgers"]["master_fact_ledger"]) == 2
    assert compiled["orphans"]["facts"] == []


def test_missing_accountability_path_stops_at_pleading_ready():
    graph = _complete_graph(accountability_ready=False)
    compiled = compile_case_graph(graph)
    assert compiled["promotion_report"]["ALG-1"] == PromotionState.PLEADING_READY.value


def test_unknown_actor_requires_identity_discovery_target():
    graph = _complete_graph()
    graph.actor_nodes["ACT-DOE-1"] = ActorNode(
        "ACT-DOE-1",
        "Unknown initiating actor",
        unknown_identity=True,
    )
    graph.packet.actors["ACT-DOE-1"] = {"id": "ACT-DOE-1"}
    errors = graph.validate()
    assert "ACT-DOE-1: unknown actor requires identity discovery target" in errors


def test_unknown_actor_with_identity_target_is_valid():
    graph = _complete_graph()
    target = DiscoveryTarget(
        "DISC-ID-1",
        "ALG-1",
        "Identity of initiating actor",
        "duty roster / access log / witness",
        "entity custodian",
        "discovery",
        "P1",
    )
    graph.add_discovery_target(target, resolved=True)
    graph.actor_nodes["ACT-DOE-1"] = ActorNode(
        "ACT-DOE-1",
        "Unknown initiating actor",
        unknown_identity=True,
        identity_discovery_target_ids=("DISC-ID-1",),
    )
    graph.packet.actors["ACT-DOE-1"] = {"id": "ACT-DOE-1"}
    graph.packet.allegations["ALG-1"].discovery_target_ids.append("DISC-ID-1")
    assert graph.validate() == []


def test_missing_fact_source_fails_before_allegation_mutation():
    graph = _complete_graph()
    graph.facts["FACT-1"] = FactProposition(
        "FACT-1",
        "Actor controlled departure.",
        ("SRC-MISSING",),
        ("ACT-DOE-1",),
        ("EVT-1",),
    )
    allegation = graph.packet.allegations["ALG-1"]
    assert allegation.promotion_state == PromotionState.RAW
    try:
        compile_case_graph(graph)
    except ValueError as exc:
        assert "FACT-1: missing source SRC-MISSING" in str(exc)
    else:
        raise AssertionError("invalid graph compiled")
    assert allegation.promotion_state == PromotionState.RAW


def test_open_high_priority_discovery_blocks_trial_ready():
    graph = _complete_graph()
    target = DiscoveryTarget(
        "DISC-GAP-1",
        "ALG-1",
        "Missing authority record",
        "authority log",
        "entity custodian",
        "discovery",
        "P0",
    )
    graph.add_discovery_target(target)
    graph.packet.allegations["ALG-1"].discovery_target_ids.append("DISC-GAP-1")
    compiled = compile_case_graph(graph)
    assert compiled["promotion_report"]["ALG-1"] == PromotionState.REFERRAL_READY.value
    graph.resolve_discovery_target("DISC-GAP-1")
    compiled = compile_case_graph(graph)
    assert compiled["promotion_report"]["ALG-1"] == PromotionState.TRIAL_READY.value


def test_open_contradiction_blocks_trial_ready_until_assessed():
    graph = _complete_graph()
    contradiction = Contradiction(
        "CONTRA-1",
        "ALG-1",
        "Official account conflicts with contemporaneous source.",
        "SRC-1",
        "SRC-3",
        "chronology",
    )
    graph.add_contradiction(
        contradiction,
        ContradictionAssessment("CONTRA-1", ContradictionState.OPEN),
    )
    old = graph.allegation_links["ALG-1"]
    graph.allegation_links["ALG-1"] = AllegationLink(
        allegation_id=old.allegation_id,
        fact_ids=old.fact_ids,
        duty_or_prohibition=old.duty_or_prohibition,
        defense_ids=old.defense_ids,
        contradiction_ids=("CONTRA-1",),
        accountability_path_ids=old.accountability_path_ids,
    )
    compiled = compile_case_graph(graph)
    assert compiled["promotion_report"]["ALG-1"] == PromotionState.REFERRAL_READY.value

    graph.contradiction_assessments["CONTRA-1"] = ContradictionAssessment(
        "CONTRA-1",
        ContradictionState.IMPEACHMENT_READY,
        impeachment_value="chronology conflict",
    )
    compiled = compile_case_graph(graph)
    assert compiled["promotion_report"]["ALG-1"] == PromotionState.TRIAL_READY.value


def test_orphan_report_exposes_unattached_source():
    graph = _complete_graph()
    graph.add_source(_source("SRC-ORPHAN"))
    assert graph.orphan_report()["sources"] == ["SRC-ORPHAN"]


def test_pressure_vector_is_multidimensional_not_hidden_composite():
    graph = _complete_graph()
    pressure = graph.pressure_vector("ALG-1")
    assert pressure["proof_strength"] == 5
    assert pressure["element_coverage"] == 1.0
    assert pressure["source_depth"] == 2
    assert pressure["defense_tested"] is True
    assert pressure["promotion_state"] == PromotionState.TRIAL_READY.value
