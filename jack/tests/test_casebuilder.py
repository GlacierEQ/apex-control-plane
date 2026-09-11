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
    assert target.gap_ids == ("GAP-1",)


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


def test_discovery_target_must_belong_to_referencing_allegation():
    packet = CasePacket("MATTER-1")
    packet.add_source(_source("SRC-1"))
    packet.add_source(_source("SRC-2"))
    packet.add_source(_source("SRC-3"))
    packet.actors["ACT-DOE-1"] = {"role": "unknown actor"}
    packet.events["EVT-1"] = {"description": "event"}
    packet.harms["HARM-1"] = {"description": "loss of use"}
    packet.remedies["REM-1"] = {"description": "damages"}
    allegation = _allegation(discovery_target_ids=["DISC-GAP-1"])
    packet.add_allegation(allegation)
    packet.add_discovery_target(
        gap_to_discovery_target(
            allegation_id="ALG-OTHER",
            gap_id="GAP-1",
            missing_fact="identity",
            record_or_witness="custody log",
            custodian="entity",
            route="discovery",
        )
    )
    errors = packet.validate()
    assert any("belongs to ALG-OTHER" in error for error in errors)


def test_compile_rejects_missing_actor_and_event_references():
    packet = CasePacket("MATTER-1")
    packet.add_source(_source("SRC-1"))
    packet.add_source(_source("SRC-2"))
    packet.add_source(_source("SRC-3"))
    packet.harms["HARM-1"] = {"description": "loss of use"}
    packet.remedies["REM-1"] = {"description": "damages"}
    packet.add_allegation(_allegation())
    errors = packet.validate()
    assert "ALG-1: missing actor ACT-DOE-1" in errors
    assert "ALG-1: missing event EVT-1" in errors


def test_blank_gap_id_is_rejected():
    try:
        gap_to_discovery_target(
            allegation_id="ALG-1",
            gap_id="   ",
            missing_fact="identity",
            record_or_witness="custody log",
            custodian="entity",
            route="discovery",
        )
    except ValueError as exc:
        assert "gap_id must be non-empty" in str(exc)
    else:
        raise AssertionError("blank gap id accepted")


def test_failed_compile_does_not_mutate_allegation():
    packet = CasePacket("MATTER-1")
    allegation = _allegation()
    packet.add_allegation(allegation)
    assert allegation.promotion_state == PromotionState.RAW
    assert allegation.impact_score == 0.0
    try:
        compile_case(packet)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid packet compiled")
    assert allegation.promotion_state == PromotionState.RAW
    assert allegation.impact_score == 0.0


def test_missing_actor_act_or_causation_blocks_pleading_ready():
    sources = {"SRC-1": _source("SRC-1"), "SRC-2": _source("SRC-2"), "SRC-3": _source("SRC-3")}
    for allegation in (
        _allegation(actor_ids=[]),
        _allegation(act=" "),
        _allegation(causation=" "),
    ):
        harden(allegation, sources)
        assert allegation.promotion_state != PromotionState.PLEADING_READY


def _packet_with(allegation):
    packet = CasePacket("MATTER-1")
    packet.add_source(_source("SRC-1"))
    packet.add_source(_source("SRC-2"))
    packet.add_source(_source("SRC-3"))
    packet.actors["ACT-DOE-1"] = {"role": "unknown actor"}
    packet.events["EVT-1"] = {"description": "event"}
    packet.harms["HARM-1"] = {"description": "loss of use"}
    packet.remedies["REM-1"] = {"description": "damages"}
    packet.add_allegation(allegation)
    return packet


def test_primary_source_proof_state_controls_promotion():
    sources = {
        "SRC-1": _source("SRC-1", ProofState.QUARANTINED),
        "SRC-2": _source("SRC-2"),
        "SRC-3": _source("SRC-3"),
    }
    allegation = _allegation()
    harden(allegation, sources)
    assert allegation.promotion_state == PromotionState.STRUCTURED


def test_satisfied_element_requires_usable_support():
    sources = {
        "SRC-1": _source("SRC-1"),
        "SRC-2": _source("SRC-2"),
        "SRC-3": _source("SRC-3"),
    }
    allegation = _allegation(
        elements=[ElementSupport("control", (), (), (), True)]
    )
    harden(allegation, sources)
    assert allegation.promotion_state == PromotionState.ELEMENT_MAPPED


def test_packet_rejects_empty_matter_and_source_key_identity_mismatch():
    packet = CasePacket("")
    packet.sources["SRC-ALIAS"] = _source("SRC-REAL")
    errors = packet.validate()
    assert "matter_id must be non-empty" in errors
    assert (
        "source map key SRC-ALIAS does not match source id SRC-REAL"
        in errors
    )


def test_invalid_discovery_priority_is_rejected():
    try:
        gap_to_discovery_target(
            allegation_id="ALG-1",
            gap_id="GAP-1",
            missing_fact="identity",
            record_or_witness="custody log",
            custodian="entity",
            route="discovery",
            priority="URGENT",
        )
    except ValueError as exc:
        assert "invalid discovery priority" in str(exc)
    else:
        raise AssertionError("invalid priority accepted")


def test_unresolved_gap_requires_matching_discovery_target():
    allegation = _allegation(missing_evidence_ids=["GAP-1"])
    packet = _packet_with(allegation)
    errors = packet.validate()
    assert "ALG-1: unresolved gap GAP-1 has no discovery target" in errors

    target = gap_to_discovery_target(
        allegation_id="ALG-1",
        gap_id="GAP-1",
        missing_fact="identity",
        record_or_witness="custody log",
        custodian="entity",
        route="discovery",
        priority="P0",
    )
    packet.add_discovery_target(target)
    allegation.discovery_target_ids.append(target.id)
    errors = packet.validate()
    assert "ALG-1: unresolved gap GAP-1 has no discovery target" not in errors


def test_duplicate_source_ids_do_not_inflate_score():
    sources = {
        "SRC-1": _source("SRC-1"),
        "SRC-2": _source("SRC-2"),
        "SRC-3": _source("SRC-3"),
    }
    unique = _allegation(corroborating_source_ids=["SRC-2"])
    repeated = _allegation(
        id="ALG-2",
        corroborating_source_ids=["SRC-2"] * 5,
    )
    harden(unique, sources)
    harden(repeated, sources)
    assert repeated.impact_score == unique.impact_score


def test_packet_validation_rejects_duplicate_source_ids():
    allegation = _allegation(corroborating_source_ids=["SRC-2", "SRC-2"])
    packet = _packet_with(allegation)
    errors = packet.validate()
    assert "ALG-1: duplicate corroborating source ids: SRC-2" in errors


def test_compiled_packet_sections_are_detached_snapshots():
    packet = _packet_with(_allegation())
    compiled = compile_case(packet)

    compiled["actors"]["ACT-DOE-1"]["role"] = "mutated"
    compiled["events"]["EVT-1"]["description"] = "mutated"
    compiled["harms"]["HARM-1"]["description"] = "mutated"
    compiled["remedies"]["REM-1"]["description"] = "mutated"

    assert packet.actors["ACT-DOE-1"]["role"] == "unknown actor"
    assert packet.events["EVT-1"]["description"] == "event"
    assert packet.harms["HARM-1"]["description"] == "loss of use"
    assert packet.remedies["REM-1"]["description"] == "damages"
