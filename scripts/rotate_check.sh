#!/bin/bash
# rotate_check.sh — Run before any commit to verify no secrets in staging area
# Usage: bash scripts/rotate_check.sh

set -e

PATTERNS=(
  "gh[pousr]_[A-Za-z0-9]{36,}"
  "secret_[A-Za-z0-9]{43}"
  "sk-[A-Za-z0-9]{48}"
  "(?i)(api_key|token|secret)[[:space:]]*=[[:space:]]*[A-Za-z0-9_\-]{20,}"
)

echo "Scanning staged files for secret patterns..."
FOUND=0

for pattern in "${PATTERNS[@]}"; do
  MATCHES=$(git diff --cached | grep -E "$pattern" || true)
  if [ -n "$MATCHES" ]; then
    echo "SECRET DETECTED in staged changes:"
    echo "$MATCHES"
    FOUND=1
  fi
done

if [ $FOUND -eq 1 ]; then
  echo ""
  echo "COMMIT BLOCKED: Remove secrets before committing."
  echo "Store in GitHub Secrets or .env (gitignored)"
  exit 1
else
  echo "Clean: no secrets in staged changes"
fi
