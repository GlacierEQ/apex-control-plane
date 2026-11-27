# PR #209 provider-native merge blocker receipt

Date: 2026-09-13
Repository: GlacierEQ/apex-control-plane
PR: #209
Recovered head: b5b97c575d9e346b00a6ab5bbd08858cdb4102fa
Base at recovery: 7f5b5763ca91cfaea0708354bf781918598cd4f8

## Verified pre-merge state
- Combined commit status: success.
- CodeRabbit: success.
- buildkite/apex-control-plane: success.
- Buildkite build #993 passed in 11m58s.
- GitHub check-runs endpoint returned 22 runs; all completed, with successful or intentionally skipped conclusions.

## Provider-native merge attempt
A squash merge was invoked through the GitHub provider API.

Exact provider response:
`failed to merge pull request: PUT https://api.github.com/repos/GlacierEQ/apex-control-plane/pulls/209/merge: 405 4 of 4 required status checks are expected. []`

## Classification
This is a GitHub/provider-native branch-protection or ruleset condition, distinct from the earlier pre-provider safety-check suppression. The current connector surface does not expose branch-protection/ruleset read APIs, so the exact four expected contexts remain unresolved from this surface.

## Continuation frontier
Resolve the four required expected contexts (missing/renamed/stale/app-bound), trigger or repair them, then merge PR #209 and read back main.