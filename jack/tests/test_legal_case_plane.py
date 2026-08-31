import json
import unittest
from unittest.mock import patch

from jack.src.legal_case_plane import (
    LegalCasePlane,
    LegalCasePlaneConfig,
    LegalCasePlaneError,
)

class _FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def read(self):
        return self.payload
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False

class LegalCasePlaneTests(unittest.TestCase):
    def setUp(self):
        self.plane = LegalCasePlane(
            LegalCasePlaneConfig("https://example.supabase.co", "test-key")
        )

    def test_rejects_unsafe_case_id(self):
        with self.assertRaises(LegalCasePlaneError):
            self.plane.get_case("../bad")

    @patch("jack.src.legal_case_plane.urlopen")
    def test_get_case_requires_exactly_one_row(self, mock_open):
        mock_open.return_value = _FakeResponse([])
        with self.assertRaises(LegalCasePlaneError):
            self.plane.get_case("CASE-1")

    @patch("jack.src.legal_case_plane.urlopen")
    def test_bundle_uses_approved_tables_and_counts(self, mock_open):
        responses = [
            [{"case_id": "CASE-1", "status": "ACTIVE"}],
            [{"actor_id": "A-1"}],
            [{"proposition_id": "P-1"}, {"proposition_id": "P-2"}],
            [{"contradiction_id": "C-1"}],
            [{"target_id": "T-1", "priority": "CRITICAL"}],
            [{"receipt_id": "R-1"}],
        ]
        mock_open.side_effect = [_FakeResponse(x) for x in responses]
        bundle = self.plane.get_bundle("CASE-1")
        self.assertEqual(bundle["counts"]["case"], 1)
        self.assertEqual(bundle["counts"]["actors"], 1)
        self.assertEqual(bundle["counts"]["propositions"], 2)
        self.assertEqual(bundle["counts"]["contradictions"], 1)
        self.assertEqual(bundle["counts"]["evidence_targets"], 1)
        self.assertEqual(bundle["counts"]["receipts"], 1)

    @patch("jack.src.legal_case_plane.urlopen")
    def test_readiness_surfaces_critical_targets(self, mock_open):
        responses = [
            [{"case_id": "CASE-1"}],
            [{"actor_id": "A-1"}],
            [{"proposition_id": "P-1"}],
            [{"contradiction_id": "C-1"}],
            [{"target_id": "T-1", "priority": "CRITICAL"},
             {"target_id": "T-2", "priority": "HIGH"}],
            [{"receipt_id": "R-1"}],
        ]
        mock_open.side_effect = [_FakeResponse(x) for x in responses]
        state = self.plane.readiness("CASE-1")
        self.assertTrue(state["case_loaded"])
        self.assertEqual(state["critical_open_targets"], 1)

if __name__ == "__main__":
    unittest.main()
