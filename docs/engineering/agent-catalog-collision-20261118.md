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
