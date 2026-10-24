# ACP Overhaul — 2026-10-24

Authorization: Operator order 2026-10-23 17:18 ("overhaul this apex control
plane and force push it"), scope limit 2026-10-23 17:23 (force push ACP
ONLY), confirmed 2026-10-24 01:29 ("ok do it").

## What was tested before anything was adopted

Sources, as claims only:
- Reddit harvest 2026-10-23: 50 posts, 51 skills, 9 MCP servers/connectors,
  36 ideas. Full results: `~/workspace/overhaul-tests/BEHAVIOR_TEST_REPORT_2026-10-24.md`.
- Grok collection 2026-10-23: 20 repos, API-verified, nothing cloned.

Verdicts (behavior-test agent, real runs):
- Activation hooks: NOT VERIFIED as numbers. Baseline 8/24 (33.3%),
  placebo 8/24 (33.3%), simple instruction 8/24 (33.3%), eval-hook
  matcher 16/24 (66.7%), forced invocation 24/24 (100%). The post's
  0/20/80/84% figures did not reproduce and do not enter doctrine.
- Code-for-control-flow: PASS on size/corruption (structured 171 chars
  vs narration 378; narration silently corrupted on a decoy probe).
- Skill Gate CI honesty: PASS (green tests + changed test bytes = gate fail).
- Breadcrumb/handoff: PARTIAL (8/8 exact vs 4/8 naive full-dump re-derivation).
- Anthropic Oct 22 alignment: PARTIAL for tool-search arithmetic
  (top-1 15/20, top-3 18/20, 94.2% context reduction); the 30-50 tool
  threshold and 80% prompt cut are NOT VERIFIED here.
- Grok #05 foreman + #18 profiles: PASS (worker self-mark rejected 3/3;
  grader PASS/BLOCK/HOLD 3/3; missing cost renders empty, never 0).
  The two share one implementation, so they are not independent experiments.

Entered the rebuild: forced invocation over generic prose; structured
phase-to-phase passing; test-byte hash gate; breadcrumb handoff format;
hard worker != grader separation with PASS/BLOCK/HOLD; refuse-to-guess;
top-k tool loading.
Rejected: the 84% figure; unconditional "subagents reduce context";
"narration always fails"; "dumps always fail"; a keyword matcher as a
load-bearing eval hook; Anthropic thresholds as measured facts.
Parked (needs an eligible LLM runner, not guessed): real Claude Code /
Haiku hook-rate replication; Anthropic LLM claims.

## Counter-design (Operator's definitions, 2026-10-23)

- Triggers run routes; they do not wait for a tap.
- Receipts are before/after state diffs.
- "Unverified" is a route that runs until it verifies or reroutes.
- Escalation survives only for: a genuine judgment call, an
  offer/acceptance, a fact only the Operator holds, or a Tier-2 log
  matter (court, agencies, administration, PACT).
- A worker never grades its own work; missing evidence renders as no
  value, never an invented number.

Attribution, standing (2026-10-23 17:09 correction): the control stack
eradicated in 2026-10-23 is the machine's handwriting, not the
Operator's build. Git author name is the separator: GlacierEQ is his lane.

## Resistances resolved in this rebuild

- (a) `tests/test_continuous_control_plane.py` (17 FileNotFoundError):
  new `config/continuous_control_plane.json` written for the overhaul
  (routes + authority only, not a restoration of the deleted config).
  All 17 tests now pass.
- (b) `src/apex_session_gateway.py` + 2 test files (collection errors):
  gateway now defines its own Recovery / ContextApplication /
  AdmissionReceipt / execute_with_recovered_context locally; the deleted
  module is not resurrected. Gateway tests use local stub journals.
  `src/connector_mission_router.py` now imports the same local function.
  All 20 gateway/store tests now collect and pass.
- (c) Dead audit CLIs: `apex_runner.py`, `apex_issue_writer.py`, and
  `src/verified_runtime_entrypoint.py` deleted (no tests imported them;
  their engine/boot modules were deleted in the eradication). Their
  audit-run publishing is superseded by before/after receipts.
  `src/control_plane.py` `__main__` now prints a proactive receipt;
  `src/sitecustomize.py` no longer runs a startup boot interception.
- (d) CI + docs: `.buildkite/pipeline.yml` and
  `.github/workflows/ci.yml` replaced with a single proactive suite
  (exact-commit check + compile + full pytest + CI receipt/digest);
  `casebrain-ci.yml`, `juggernaut-jack-portability.yml`,
  and `spiral-real-journal.yml` had dead file references removed;
  the one brittle old-contract Buildkite test (6-step resolver count)
  was updated to the new single-step contract, and
  `scripts/validate_buildkite_master.py` passes all 19 policy/pipeline
  checks on the new pipeline;
  `README.md`, `STATE.md`, and `AGENTS.md` dead startup references replaced.
- (e) `.integrity/file_hashes.json` survives untouched as the
  pre-eradication receipt (88 entries; 65 match, 13 missing = exactly
  the eradicated files, 10 changed = 5 eradication edits + 5 later
  upstream edits; zero unexplained differences, per census recovery).

## New code

- `src/apex_proactive.py`: Trigger, run_until_verified, StateReceipt,
  grade (worker != grader), render_value, run_phases, Breadcrumb,
  top_k_tools, SkillRegistry, snapshot_files / changed_test_files.
- `tests/test_apex_proactive.py`: 10 tests covering the above.

## Test suite, before / after (same command, repo root)

Before (census baseline, 2026-10-24): collected 799, passed 760,
failed 17, skipped 22, plus 2 collection errors (20 gateway tests
never collected) = 819 known definitions.
After (this rebuild): 807 passed, 0 failed, 22 skipped, 0 collection
errors = 829 collected. Delta +47 passed = 17 continuous + 20 gateway
+ 10 proactive. Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ -p no:cacheprovider`.

## What this rebuild does not do

- No Tier-2 log instrument, NEX/1FDV casework, or job pipeline file
  was touched.
- No harvest figure that failed verification was adopted.
- No other repository was force-pushed or history-rewritten.
