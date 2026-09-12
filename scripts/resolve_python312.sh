#!/usr/bin/env bash
set -euo pipefail

# Resolve Python 3.12 from the worker that will actually execute the job.
# An explicit override is advisory only: it must still pass local readback.
candidates=(
  "${GLACIEREQ_PYTHON312:-}"
  "/opt/homebrew/bin/python3.12"
  "/usr/local/bin/python3.12"
)

path_candidate="$(command -v python3.12 2>/dev/null || true)"
candidates+=("$path_candidate")

for candidate in "${candidates[@]}"; do
  [ -n "$candidate" ] || continue
  [ -x "$candidate" ] || continue
  if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
    "$candidate" -c 'import os, sys; print(os.path.realpath(sys.executable))'
    exit 0
  fi
done

echo "PYTHON_RUNTIME_UNRESOLVED: no locally verified Python 3.12 interpreter on this Buildkite worker" >&2
exit 78
