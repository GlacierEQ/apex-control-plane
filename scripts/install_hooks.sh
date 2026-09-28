#!/bin/bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Use a tracked hook directory so the enforcement is versioned with the repo
# instead of disappearing inside one workstation's .git directory.
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit

echo "APEX tracked hooks installed: core.hooksPath=.githooks"
echo "Pre-commit now blocks secret leakage and operator-fidelity regression."
