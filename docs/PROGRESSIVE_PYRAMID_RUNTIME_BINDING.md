# Progressive Pyramid source binding — APEX startup

Canonical Skill: `GlacierEQ/mega-skills/skills/progressive-pyramid`.
Historical persona Four Corners are preserved in `GlacierEQ/elysium-hub`.
This is the additional progressive execution projection, not a replacement
of APEX's existing boot, working model, evidence gates or Operator authority.

`config/apex_enforced_startup_policy.json` contains the exact canonical
GitHub revision and SHA-256 hashes for SKILL.md, the JSON contract, and the
real validation script. `src/progressive_pyramid_source.py` independently
reads the installed Skill and returns LOADED only when every file, revision
and schema identity match. Set `PROGRESSIVE_PYRAMID_SKILL_DIR` to explicitly
choose another installation; default is `~/.agents/skills/progressive-pyramid`.

The existing startup request now includes the observed source status and
contract hash. A missing or stale installation is reported UNAVAILABLE or
MISMATCH, never silently upgraded into successful startup verification.
Incomplete startup proof is still not an invented veto over unrelated
Operator-authorized work; it does prohibit claiming that a mission has
a verified Progressive Pyramid contract.

`validate_pyramid_run(run, lock, verifier=host_native_verifier)` executes
the pinned canonical structural validator and requires separately verified
receipts for every declared terminal acceptance criterion. Its host
callback must actually verify provider evidence. A self-reported status
does not count. APEX startup receipts cannot independently claim
MISSION_COMPLETE; mission outcomes are the responsibility of the actual
mission runner and provider verifier, not startup narration.

See `tests/test_progressive_pyramid_integration.py` for source tampering,
missing installs, false completion, and real validator coverage. Cross-agent
cold-start certification requires separate observed execution for each host.
