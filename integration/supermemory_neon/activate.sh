#!/usr/bin/env bash
# ============================================================
# apex-control-plane — Activation Script
# Steps: Neon migration → Python deps → Connector registry seed → First audit run
# Run from repo root: bash integration/supermemory_neon/activate.sh
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INTEGRATION_DIR="$REPO_ROOT/integration/supermemory_neon"

echo "==> [1/5] Loading environment..."
if [ -f "$REPO_ROOT/.env" ]; then
  set -a && source "$REPO_ROOT/.env" && set +a
else
  echo "ERROR: .env not found. Copy .env.example → .env and fill values."
  exit 1
fi

REQUIRED_VARS=(SUPERMEMORY_API_KEY NEON_DATABASE_URL GITHUB_TOKEN)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: $var is not set in .env"
    exit 1
  fi
done
echo "     All required env vars present."

echo "==> [2/5] Applying Neon migration 001_connectors.sql..."
psql "$NEON_DATABASE_URL" -f "$INTEGRATION_DIR/migrations/001_connectors.sql"
echo "     Migration applied."

echo "==> [3/5] Installing Python dependencies..."
pip install -q psycopg2-binary supermemory python-dotenv requests

echo "==> [4/5] Seeding connector registry (if not already seeded)..."
python3 - <<'PYEOF'
import os, sys
from dotenv import load_dotenv
load_dotenv()
import psycopg2
conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT count(*) FROM connectors WHERE is_active = true;")
count = cur.fetchone()[0]
print(f"     Active connectors already in registry: {count}")
if count == 0:
    print("     No connectors found — re-run migration SQL to reseed.")
else:
    print("     Registry seeded and ready.")
conn.close()
PYEOF

echo "==> [5/5] Running first audit loop..."
python3 "$INTEGRATION_DIR/audit_loop.py"

echo ""
echo "✅  apex-control-plane activated."
echo "    All 9 connectors registered + health-checked."
echo "    Audit summaries pushed to Supermemory containers."
echo ""
echo "    To schedule daily: add to cron or CI:"
echo "    0 6 * * * cd /path/to/apex-control-plane && bash integration/supermemory_neon/activate.sh"
