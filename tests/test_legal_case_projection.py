from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.legal_case_projection import (
    LegalCaseProjection,
    LegalCaseProjectionConfig,
    LegalCaseProjectionError,
)


class _FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def plane() -> LegalCaseProjection:
    return LegalCaseProjection(
        LegalCaseProjectionConfig("https://example.supabase.co", "test-key")
    )


def test_rejects_unsafe_case_id() -> None:
    with pytest.raises(LegalCaseProjectionError, match="invalid case_id"):
        plane().get_case("../bad")


@patch("src.legal_case_projection.urlopen")
def test_bundle_reads_only_approved_case_scoped_tables(mock_open) -> None:
    mock_open.side_effect = [
        _FakeResponse([{"case_id": "CASE-1", "status": "ACTIVE"}]),
        _FakeResponse([{"actor_id": "A-1"}]),
        _FakeResponse([{"proposition_id": "P-1"}, {"proposition_id": "P-2"}]),
        _FakeResponse([{"contradiction_id": "C-1"}]),
        _FakeResponse([{"target_id": "T-1", "priority": "CRITICAL"}]),
        _FakeResponse([{"receipt_id": "R-1"}]),
    ]
    bundle = plane().get_bundle("CASE-1")
    assert bundle["counts"] == {
        "case": 1,
        "actors": 1,
        "propositions": 2,
        "contradictions": 1,
        "evidence_targets": 1,
        "receipts": 1,
    }
    assert bundle["projection_semantics"]["authority"] == "mission_projection_only"
    assert bundle["projection_semantics"]["source_bound_case_records_retain_authority"] is True
    assert all(request.method == "GET" for request in [call.args[0] for call in mock_open.call_args_list])


@patch("src.legal_case_projection.urlopen")
def test_readiness_surfaces_structure_without_promoting_projection_authority(mock_open) -> None:
    mock_open.side_effect = [
        _FakeResponse([{"case_id": "CASE-1"}]),
        _FakeResponse([{"actor_id": "A-1"}]),
        _FakeResponse([{"proposition_id": "P-1"}]),
        _FakeResponse([]),
        _FakeResponse([
            {"target_id": "T-1", "priority": "CRITICAL"},
            {"target_id": "T-2", "priority": "HIGH"},
        ]),
        _FakeResponse([{"receipt_id": "R-1"}]),
    ]
    state = plane().readiness("CASE-1")
    assert state["case_loaded"] is True
    assert state["critical_targets"] == 1
    assert state["authority"] == "mission_projection_only"
