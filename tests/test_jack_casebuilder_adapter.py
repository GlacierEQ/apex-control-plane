from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jack_casebuilder_adapter import CaseBuilderAdapterError, build_projection, validate_casebuilder

def fixture():
    return {
      "schema_version":"1.0",
      "case":{"case_id":"C1","title":"Case","jurisdiction":"Court","posture":"active","objective":"advance"},
      "sources":[{"source_id":"S1"}],
      "actors":[{"actor_id":"A1"}],
      "events":[{"event_id":"E1","actor_ids":["A1"],"source_ids":["S1"],"fact_ids":["F1"],"allegation_ids":["L1"]}],
      "facts":[{"fact_id":"F1","source_ids":["S1"],"event_ids":["E1"],"actor_ids":["A1"]}],
      "allegations":[{"allegation_id":"L1","actor_ids":["A1"],"event_ids":["E1"],
        "elements":[{"element_id":"EL1","description":"duty","status":"PROVEN","supporting_fact_ids":["F1"],"source_ids":["S1"],"discovery_target_ids":[]}],
        "supporting_fact_ids":["F1"],"primary_source_ids":["S1"],"corroborating_source_ids":[],"contradictory_source_ids":[],
        "defenses":["best defense"],"harm_ids":["H1"],"missing_evidence":[],"discovery_target_ids":[],
        "remedy_ids":["R1"],"accountability_path_ids":["AC1"],"next_use":["motion"],
        "promotion_state":"PLEADING_READY","tier":1}],
      "contradictions":[],
      "damages":[{"damage_id":"H1","causal_event_ids":["E1"],"causal_allegation_ids":["L1"],"source_ids":["S1"]}],
      "discovery_targets":[],
      "remedies":[{"remedy_id":"R1","predicate_allegation_ids":["L1"]}],
      "accountability_paths":[{"accountability_path_id":"AC1","predicate_allegation_ids":["L1"]}]
    }

def test_valid_projection_exposes_anchor():
    p = build_projection(fixture())
    assert p.case_id == "C1"
    assert p.anchor_allegation_ids == ("L1",)
    assert p.pleading_ready_ids == ("L1",)

def test_loose_allegation_is_rejected():
    data = fixture()
    data["allegations"][0]["defenses"] = []
    try:
        validate_casebuilder(data)
    except CaseBuilderAdapterError as exc:
        assert "defenses cannot be empty" in str(exc)
    else:
        raise AssertionError("loose allegation should fail")

def test_unknown_source_is_rejected():
    data = fixture()
    data["allegations"][0]["primary_source_ids"] = ["MISSING"]
    try:
        validate_casebuilder(data)
    except CaseBuilderAdapterError as exc:
        assert "unknown source" in str(exc)
    else:
        raise AssertionError("unknown source should fail")
