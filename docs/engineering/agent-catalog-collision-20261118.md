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
