from jack.src.casebuilder import (
    Allegation, CasePacket, ElementSupport, Lane, ProofState, PromotionState,
    SourceRef, compile_case, gap_to_discovery_target, harden,
)


def _source(i: str, state=ProofState.VERIFIED_PRIMARY):
    return SourceRef(i, "record", f"source:{i}", state)


def _allegation(**overrides):
    data = dict(
        id="ALG-1",
        title="Continued deprivation",
        lane=Lane.CIVIL,
        actor_ids=["ACT-DOE-1"],
        event_ids=["EVT-1"],
        act="Retained property after asserted authority ended.",
        factual_theory="Property remained unavailable after notice and demand.",
        legal_theory="Property deprivation theory.",
        elements=[ElementSupport("control", ("SRC-1",), (), (), True)],
        primary_source_ids=["SRC-1"],
        corroborating_source_ids=["SRC-2"],
        contradictory_source_ids=["SRC-3"],
        causation="Retention caused loss of use.",
        harm_ids=["HARM-1"],
        defenses=["continued authority"],
        rebuttals=["no current authority produced"],
        remedy_ids=["REM-1"],
        proof_state=ProofState.CORROBORATED,
    )
    data.update(overrides)
    return Allegation(**data)


def test_gap_becomes_discovery_target():
    target = gap_to_discovery_target(
        allegation_id="ALG-1",
        gap_id="GAP-1",
        missing_fact="identity of custodian",
        record_or_witness="custody log",
        custodian="entity",
        route="discovery",
    )
    assert target.id == "DISC-GAP-1"
    assert target.allegation_id == "ALG-1"


def test_mental_state_blocks_high_promotion_without_support():
    sources = {"SRC-1": _source("SRC-1"), "SRC-2": _source("SRC-2"), "SRC-3": _source("SRC-3")}
    a = _allegation(mental_state_required="knowingly", mental_state_source_ids=[])
    harden(a, sources)
    assert a.promotion_state == PromotionState.DEFENSE_TESTED


def test_complete_supported_allegation_becomes_pleading_ready():
    sources = {"SRC-1": _source("SRC-1"), "SRC-2": _source("SRC-2"), "SRC-3": _source("SRC-3")}
    a = _allegation()
    harden(a, sources)
    assert a.promotion_state == PromotionState.PLEADING_READY
    assert a.impact_score > 0


def test_quarantined_never_promotes():
    sources = {"SRC-1": _source("SRC-1"), "SRC-2": _source("SRC-2"), "SRC-3": _source("SRC-3")}
    a = _allegation(proof_state=ProofState.QUARANTINED)
    harden(a, sources)
    assert a.promotion_state == PromotionState.RAW


def test_compile_requires_cross_reference_integrity():
    packet = CasePacket("MATTER-1")
    packet.add_source(_source("SRC-1"))
    packet.add_source(_source("SRC-2"))
    packet.add_source(_source("SRC-3"))
    packet.actors["ACT-DOE-1"] = {"role": "unknown actor"}
    packet.events["EVT-1"] = {"description": "event"}
    packet.harms["HARM-1"] = {"description": "loss of use"}
    packet.remedies["REM-1"] = {"description": "damages"}
    packet.add_allegation(_allegation())
    compiled = compile_case(packet)
    assert compiled["metrics"]["pleading_ready"] == 1


def test_compile_rejects_missing_source():
    packet = CasePacket("MATTER-1")
    packet.actors["ACT-DOE-1"] = {"role": "unknown actor"}
    packet.events["EVT-1"] = {"description": "event"}
    packet.harms["HARM-1"] = {"description": "loss of use"}
    packet.remedies["REM-1"] = {"description": "damages"}
    packet.add_allegation(_allegation())
    try:
        compile_case(packet)
    except ValueError as exc:
        assert "missing source SRC-1" in str(exc)
    else:
        raise AssertionError("invalid packet compiled")
