#!/usr/bin/env bash
set -euo pipefail

# Resolve Python 3.12 from the worker that will actually execute the job.
# Discovery sources are hints only: every candidate must prove its own version
# through executable readback before it can authorize downstream CI execution.
candidates=()

add_candidate() {
  local candidate="${1:-}"
  [ -n "$candidate" ] || return 0
  candidates+=("$candidate")
}

add_candidate "${GLACIEREQ_PYTHON312:-}"
add_candidate "$(command -v python3.12 2>/dev/null || true)"

# Ask worker-local runtime managers for their actual installation topology
# instead of assuming Intel or Apple-Silicon Homebrew prefixes.
if command -v brew >/dev/null 2>&1; then
  brew_prefix="$(brew --prefix python@3.12 2>/dev/null || true)"
  [ -n "$brew_prefix" ] && add_candidate "$brew_prefix/bin/python3.12"
fi
if command -v pyenv >/dev/null 2>&1; then
  add_candidate "$(pyenv which python3.12 2>/dev/null || true)"
fi
if command -v mise >/dev/null 2>&1; then
  add_candidate "$(mise which python@3.12 2>/dev/null || true)"
  add_candidate "$(mise which python3.12 2>/dev/null || true)"
fi
if command -v asdf >/dev/null 2>&1; then
  add_candidate "$(asdf which python3.12 2>/dev/null || true)"
fi

# Last-resort conventional locations remain probes, never authority.
add_candidate "/opt/homebrew/bin/python3.12"
add_candidate "/usr/local/bin/python3.12"
add_candidate "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"

seen="|"
for candidate in "${candidates[@]}"; do
  [ -n "$candidate" ] || continue
  case "$seen" in
    *"|$candidate|"*) continue ;;
  esac
  seen="${seen}${candidate}|"
  [ -x "$candidate" ] || continue
  if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
    "$candidate" -c 'import os, sys; print(os.path.realpath(sys.executable))'
    exit 0
  fi
done

echo "PYTHON_RUNTIME_UNRESOLVED: worker-local capability discovery found no executable Python 3.12 runtime" >&2
exit 78
