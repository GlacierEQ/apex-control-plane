from __future__ import annotations

import unittest

from scripts.repo_history_continuity import validate_result


class RepoHistoryContinuityTests(unittest.TestCase):
    def test_clean_ancestry_is_accepted(self) -> None:
        changed, suspects = validate_result(
            {
                "ok": True,
                "status": "audited",
                "snapshot_id": "current",
                "previous_snapshot_id": "previous",
                "changed_head_count": 3,
                "suspect_count": 0,
                "classifications": {"ANCESTRY_PRESERVED": 3},
                "github_writes": 0,
                "token_persisted": False,
            }
        )
        self.assertEqual(changed, 3)
        self.assertEqual(suspects, 0)

    def test_suspect_history_is_evidence_not_protocol_failure(self) -> None:
        changed, suspects = validate_result(
            {
                "ok": True,
                "status": "audited",
                "snapshot_id": "current",
                "previous_snapshot_id": "previous",
                "changed_head_count": 4,
                "suspect_count": 3,
                "classifications": {
                    "ANCESTRY_PRESERVED": 1,
                    "REWRITE_SUSPECT": 1,
                    "ROLLBACK_SUSPECT": 1,
                    "PRIOR_HEAD_UNREACHABLE": 1,
                },
                "github_writes": 0,
                "token_persisted": False,
            }
        )
        self.assertEqual(changed, 4)
        self.assertEqual(suspects, 3)

    def test_github_write_claim_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            validate_result(
                {
                    "ok": True,
                    "status": "audited",
                    "snapshot_id": "current",
                    "previous_snapshot_id": "previous",
                    "changed_head_count": 0,
                    "classifications": {},
                    "github_writes": 1,
                    "token_persisted": False,
                }
            )

    def test_classification_total_mismatch_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            validate_result(
                {
                    "ok": True,
                    "status": "audited",
                    "snapshot_id": "current",
                    "previous_snapshot_id": "previous",
                    "changed_head_count": 2,
                    "classifications": {"ANCESTRY_PRESERVED": 1},
                    "github_writes": 0,
                    "token_persisted": False,
                }
            )

    def test_unexpected_fields_are_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            validate_result(
                {
                    "ok": True,
                    "status": "audited",
                    "snapshot_id": "current",
                    "previous_snapshot_id": "previous",
                    "changed_head_count": 0,
                    "classifications": {},
                    "github_writes": 0,
                    "token_persisted": False,
                    "write_branch": "main",
                }
            )


if __name__ == "__main__":
    unittest.main()
