# Agent cleanup classification — 2026-11-21

Recovered stronger agent-inspector-terminal-status-20261120 branch at b65a428; remote scheduler branch f5659af is older and does not contain the later subprocess executor. Do not rebase onto that weaker branch.

Changed executable consumer: a zero-exit subprocess with incomplete output or unresolved owned cleanup is now failure-classified (74), rather than process_succeeded_unverified. Existing nonzero and timeout outcomes are unchanged.

Verification: py_compile and git diff --check passed. Focused pytest initially ran 10 pass/1 fail due to missing src import path; subsequent invocation lacked pytest in the selected Python environment. Full changed-head tests remain REQUIRED; no runtime deployment claim.

Next: recover Python 3.13 pytest environment, run focused and full suite, add fault-injection regression for cleanup_unresolved with zero exit, then connect receipt inspector to scheduler adapter. No merge/deploy.
