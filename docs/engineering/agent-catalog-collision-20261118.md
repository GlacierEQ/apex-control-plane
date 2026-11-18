# Agent tool routing collision repair — 2026-11-18

Owner: apex-control-plane, standalone `src/tool_catalog.py`. No Omni_Engine provider or continuity bridge modified.

## Recovered source behavior
`select()` constructed a dictionary keyed only by entry name, so two entries named alike (skill vs connector, or duplicated connector) silently selected the last enumerated entry. `hot_swap()` delegates to `select()`, propagating the same wrong-tool routing hazard.

## Change and acceptance
- Preserve bare-name selection for unique names and unknown-name omission.
- Accept explicit `skill:name` / `connector:name` routing.
- Reject ambiguous bare names and even duplicate qualified names with a deterministic `ValueError`, rather than silently invoking the wrong tool.
- Preserve catalog enumeration, no caps, and hot-swap behavior.

Implementation: `src/tool_catalog.py`. Regression tests: `tests/test_tool_catalog_collision.py`.

## Verification boundary / next cursor
Provider-native GitHub write and file readback required; regression tests are authored but no changed-head CI or runtime execution is claimed here. Next: execute `python -m pytest -q tests/test_tool_catalog_collision.py` plus existing catalog tests on exact branch head, inspect output and exercise consumer integration. Do not merge or deploy without authorization.

## Follow-on correction — repeated selection deduplication (2026-11-18)
`select()` now keeps the first occurrence of each unique `(kind, name, path)` capability when callers repeat a bare name, qualified name, or both. This prevents redundant loading of the same agent capability while preserving first-request ordering, unique-name compatibility, collision rejection, and hot-swap semantics. Added regression coverage for mixed bare/qualified duplicates and hot swap. Provider commits: `5eb529acc19538312a2c0b0822f7cc0f4831a08a` (implementation) and `796130307700e50a209e9fec2fafbde9ca5fe9e4` (test). Exact changed-head test execution and live consumer routing remain unverified. Next: run existing and new catalog tests at head `7961303`, then exercise the actual loader with repeated selection requests and confirm only one capability is loaded. No merge/deploy.

## 2026-11-18 exact-head execution and colon-name repair
Recovered PR #377 and cloned the branch onto the connected Mac under `/Users/kcbflux/Documents/GlacierEQ-Agent-Engineering-20261118/apex-control-plane`. The pre-change head `d5097b70` passed the full repository test suite (1054 passed, 29 skipped, 8 subtests). Found an additional live routing defect: literal capability names containing colons could not be selected as bare names. Fixed namespace resolution to consider both literal and qualified matches, reject conflicting interpretations, and preserve distinct duplicate-entry rejection. The first attempt incorrectly collapsed equal-valued distinct entries; changed-head regression detected this (1 failed), and the correction now deduplicates only the same entry object observed through both lookup indexes.

GitHub implementation commits: `eefba53cf7c6438e0fecc5f4fd18a6da1a44f94b`, `de182fb8032115a23f84203d8de0106410e06d39`, `399ba0371f45dc4c5b63646e5caaba2f7bd3f240`. Exact changed-head Mac test at `399ba0371f45dc4c5b63646e5caaba2f7bd3f240`: `uv run --no-project --with pytest python -m pytest -q tests` -> **1056 passed, 29 skipped, 8 subtests passed**. No deployment or real agent host invocation verified. Continuation: inspect whether production consumer imports `src/tool_catalog.py` or another router; test actual consumer tool-loading boundary before claiming integrated capability. No merge or task changes.

## 2026-11-18 independent exact-head verification
Independently fetched GitHub branch head `34604026313bade3be301a9fe771752c6e6c4e27` using `git ls-remote`, cloned into `/Users/kcbflux/Documents/GlacierEQ-Agent-Validation/apex-control-plane`, and checked out that exact revision. The initial `python3` invocation used Homebrew Python 3.15 without pytest; switched to installed Python 3.13 instead of treating this environment mismatch as a source defect. `python3.13 -m pytest -q tests/test_tool_catalog.py`: **6 passed, 1 skipped**. Full exact-head `python3.13 -m pytest -q`: **1083 passed, 29 skipped, 8 subtests passed**, exit 0, in 5.99 seconds. This supersedes the earlier unverified test claim for this branch head; it does not establish deployed host integration. Default-branch GitHub code search found `tool_catalog` referenced in documentation and tests, but no consumer calling `select()` beyond tests; README says the proactive engine was intentionally removed on 2026-10-24 following failed live-job proof. Do not resurrect that removed engine or claim a live loader. Next: recover the currently authorized runtime's actual capability-loading entrypoint and integrate the tested routing behavior there, with a real boundary test. No merge, deployment, automation edits, or other workstream changes.


## 2026-11-18 overlapping-root discovery repair
Recovered PR #377, branch implementation, catalog tests, and the default-branch absence of a real catalog consumer. Identified a new operational catalog failure: when agent discovery receives overlapping skill/connector roots or an alias to the same root, `build_catalog()` emits the same underlying document multiple times. The existing fail-closed `select()` then rejects a valid unique capability as ambiguous. This is a source-level discoverability defect, not a reason to weaken collision detection.

Changed `build_catalog()` to deduplicate by (kind, resolved document path), preserving distinct files with the same name as genuine ambiguity. Implementation commit `60c2871ad8911781bfd18e836da3f8c376c7ea4d`; regression tests commit `6d97d2b0be363dc4f1f47e08f5789bb78cd74995`. On connected Mac, checked out exact GitHub revision `6d97d2b`: focused catalog suites **14 passed, 1 skipped**, full repository **1085 passed, 29 skipped, 8 subtests passed**, exit 0. This fixes duplicate discovery for any caller of `build_catalog()`; it does not establish host invocation or a production loader. Next: identify an actually authorized active capability discovery consumer and test end-to-end loading; do not revive the removed proactive engine. No merge, deployment, task or permission changes.
