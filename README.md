# APEX Control Plane

**Autonomous daily audit loop for the GlacierEQ sovereign operator system.**

No manual approval required. Runs every day at 08:00 HST automatically.

## What It Does Daily

| Layer | Task | Output |
|-------|------|---------|
| 1 | Connector Validation | GREEN/RED status per service |
| 2 | Secret Leakage Scan | P0 findings w/ file:line evidence |
| 3 | Drift Detection | P1 CI/CD and endpoint drift issues |
| 4 | Action Queue | Ranked immediate/strategic/backlog |
| 5 | Audit Log | Append-only JSON in `audit_logs/` |
| 6 | GitHub Issues | Auto-opens P0 issue if found |

## Secrets Required (GitHub Repo Secrets)

```
APEX_GITHUB_TOKEN   — fine-grained PAT with repo + issues scope
APEX_NOTION_TOKEN   — Notion integration token (optional)
```

## Architecture

```
daily_audit.py          ← Main autonomous runner
connector_registry.json ← Source of truth for all connectors
audit_logs/             ← Append-only run records (committed daily)
.github/workflows/
  daily-audit.yml       ← Cron: 08:00 HST daily + workflow_dispatch
```

## Philosophy

- **No confirmation required.** The system acts, logs, and escalates.
- **Reality firewall.** Every action cites a real endpoint or file path.
- **Single source of truth.** `connector_registry.json` owns connector state.
- **Fail loudly on P0.** GitHub issue auto-opens for any critical finding.

---
*GlacierEQ Sovereign Operator Stack | Casey Barton*
