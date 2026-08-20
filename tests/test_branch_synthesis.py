from __future__ import annotations

import json

import pytest

from scripts.branch_synthesis import (
    BranchSynthesisError,
    _next_link,
    branch_family_key,
    inventory_repository,
    synthesis_report,
    write_report,
)

SHA_MAIN = "1" * 40


class FakeGitHub:
    def __init__(self, *, branches, comparisons, default="main", embedded_head=False):
        self._branches = branches
        self._comparisons = comparisons
        self._default = default
        self._embedded_head = embedded_head

    def repository(self, repository):
        payload = {"default_branch": self._default}
        if self._embedded_head:
            payload["default_branch_commit"] = {"sha": SHA_MAIN}
        return payload

    def branches(self, repository):
        return list(self._branches)

    def compare(self, repository, base, head):
        assert base == self._default
        return self._comparisons[head]


def branch(name, sha, protected=False):
    return {"name": name, "commit": {"sha": sha}, "protected": protected}


def comparison(status, ahead, behind, *paths):
    return {
        "status": status,
        "ahead_by": ahead,
        "behind_by": behind,
        "files": [{"filename": path} for path in paths],
    }


def test_best_of_worlds_classifies_and_preserves_unique_donors():
    reader = FakeGitHub(
        branches=[
            branch("main", SHA_MAIN),
            branch("feature/timeline", "2" * 40),
            branch("recovery/forensic-execution", "3" * 40),
            branch("old/already-in-main", "4" * 40),
        ],
        comparisons={
            "feature/timeline": comparison("ahead", 3, 0, "timeline/engine.py", "tests/test_timeline.py"),
            "recovery/forensic-execution": comparison("diverged", 5, 12, "evidence/contradiction.py"),
            "old/already-in-main": comparison("behind", 0, 20, "README.md"),
        },
    )
    inventory = inventory_repository(reader, "GlacierEQ/legal")
    by_name = {row.name: row for row in inventory.branches}

    assert by_name["feature/timeline"].action == "PRESERVE_AND_SYNTHESIZE"
    assert by_name["recovery/forensic-execution"].action == "PRESERVE_AND_FRESH_SYNTHESIZE"
    assert by_name["old/already-in-main"].action == "RETIRE_AFTER_REACHABILITY_PROOF"
    assert inventory.preservation_set == (
        "feature/timeline",
        "recovery/forensic-execution",
    )
    assert inventory.retirement_candidates == ("old/already-in-main",)


def test_diverged_branch_is_ranked_above_forward_branch_when_capability_rich():
    reader = FakeGitHub(
        branches=[branch("main", SHA_MAIN), branch("forward", "2" * 40), branch("diverged", "3" * 40)],
        comparisons={
            "forward": comparison("ahead", 1, 0, "README.md"),
            "diverged": comparison("diverged", 1, 30, "evidence/timeline.py", "tests/test_timeline.py"),
        },
    )
    inventory = inventory_repository(reader, "GlacierEQ/legal")
    assert inventory.branches[0].name == "diverged"
    assert "legal-intelligence" in inventory.branches[0].capability_signals
    assert "tests" in inventory.branches[0].capability_signals


def test_ambiguous_compare_state_fails_closed_into_preservation():
    reader = FakeGitHub(
        branches=[branch("main", SHA_MAIN), branch("mystery", "2" * 40)],
        comparisons={"mystery": comparison("behind", 2, 7, "x.py")},
    )
    row = {row.name: row for row in inventory_repository(reader, "GlacierEQ/legal").branches}["mystery"]
    assert row.relation == "REVIEW_REQUIRED"
    assert row.action == "PRESERVE_PENDING_REVIEW"


def test_family_key_groups_agent_iteration_suffixes_without_using_them_as_disposal_proof():
    branches = [
        "innovation/worker-turn-06-runtime-semantic-gate-2026-08-07-final",
        "innovation/worker-turn-06-runtime-semantic-gate-2026-08-07-live",
    ]
    assert branch_family_key(branches[0]) == branch_family_key(branches[1])


def test_extinct_line_sha_suffixes_group_conservatively():
    assert branch_family_key("recovery/extinct-line-2026-07-23-711ea3a") == branch_family_key(
        "recovery/extinct-line-2026-07-23-bbfac4e"
    )


def test_inventory_digest_is_stable_across_branch_listing_order():
    comparisons = {
        "a": comparison("ahead", 1, 0, "a.py"),
        "b": comparison("behind", 0, 2, "b.py"),
    }
    first = FakeGitHub(
        branches=[branch("main", SHA_MAIN), branch("a", "2" * 40), branch("b", "3" * 40)],
        comparisons=comparisons,
    )
    second = FakeGitHub(
        branches=[branch("b", "3" * 40), branch("main", SHA_MAIN), branch("a", "2" * 40)],
        comparisons=comparisons,
    )
    assert inventory_repository(first, "GlacierEQ/legal").inventory_sha256 == inventory_repository(
        second, "GlacierEQ/legal"
    ).inventory_sha256


def test_default_head_disagreement_is_fatal():
    reader = FakeGitHub(
        branches=[branch("main", "9" * 40)],
        comparisons={},
        embedded_head=True,
    )
    with pytest.raises(BranchSynthesisError, match="default-head sources disagree"):
        inventory_repository(reader, "GlacierEQ/legal")


def test_duplicate_branch_names_are_rejected():
    reader = FakeGitHub(
        branches=[branch("main", SHA_MAIN), branch("main", SHA_MAIN)],
        comparisons={},
    )
    with pytest.raises(BranchSynthesisError, match="duplicate names"):
        inventory_repository(reader, "GlacierEQ/legal")


def test_invalid_branch_sha_is_rejected_before_comparison():
    reader = FakeGitHub(
        branches=[branch("main", SHA_MAIN), branch("broken", "not-a-sha")],
        comparisons={"broken": comparison("ahead", 1, 0)},
    )
    with pytest.raises(BranchSynthesisError, match="invalid GlacierEQ/legal:broken head SHA"):
        inventory_repository(reader, "GlacierEQ/legal")


def test_synthesis_report_emits_metadata_not_patch_or_file_contents():
    reader = FakeGitHub(
        branches=[branch("main", SHA_MAIN), branch("donor", "2" * 40)],
        comparisons={"donor": comparison("ahead", 1, 0, "evidence/timeline.py")},
    )
    report = synthesis_report([inventory_repository(reader, "GlacierEQ/legal")])
    assert report["schema"] == "APEX_BRANCH_SYNTHESIS_V1"

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield str(key).casefold()
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    report_keys = set(keys(report))
    assert "patch" not in report_keys
    assert "content" not in report_keys
    assert report["donor_count"] == 1


def test_atomic_report_write_round_trips(tmp_path):
    path = tmp_path / "nested" / "synthesis.json"
    write_report(path, {"schema": "x", "rows": list(range(50))})
    assert json.loads(path.read_text()) == {"schema": "x", "rows": list(range(50))}
    assert not list(path.parent.glob(".*.tmp"))


def test_next_link_parses_github_pagination():
    header = '<https://api.github.com/x?page=2>; rel="next", <https://api.github.com/x?page=4>; rel="last"'
    assert _next_link(header) == "https://api.github.com/x?page=2"
    assert _next_link(None) is None


def test_repository_identity_must_be_exact_owner_name():
    reader = FakeGitHub(branches=[branch("main", SHA_MAIN)], comparisons={})
    with pytest.raises(BranchSynthesisError, match="invalid repository identity"):
        inventory_repository(reader, "GlacierEQ/legal/extra")
