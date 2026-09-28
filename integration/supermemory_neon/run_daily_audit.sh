#!/usr/bin/env bash
# ============================================================
# apex-control-plane — Daily Audit Runner
# Runs the audit loop only (assumes activation already done).
# Suitable for cron / GitHub Actions / systemd timer.
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INTEGRATION_DIR="$REPO_ROOT/integration/supermemory_neon"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a && source "$REPO_ROOT/.env" && set +a
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Running apex daily audit..."
python3 "$INTEGRATION_DIR/audit_loop.py"
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Audit complete."
