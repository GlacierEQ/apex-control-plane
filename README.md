# APEX Control Plane

**Fully autonomous daily audit loop for GlacierEQ sovereign operator system.**

Runs every day at 08:00 UTC (10:00 PM HST). Zero human approval required.

## What it does

1. **Connector Validation** — GitHub, Notion, Supabase, OpenAI
2. **Secret Leakage Scan** — scans all source files for exposed credentials
3. **Structural Analysis** — missing .gitignore, .env.example, audit_log, README
4. **Auto-Execute Remediations** — fixes P1/P2 issues automatically, no prompts
5. **Persist Audit Log** — writes `audit_log/run_YYYY-MM-DD.json`
6. **Auto-Create GitHub Issues** — P0/P1 findings become issues automatically

## Triggers

- **Scheduled**: daily at 08:00 UTC
- **Manual**: `Actions → APEX Daily Autonomous Loop → Run workflow`

## Setup

Add these repository secrets (Settings → Secrets → Actions):

```
NOTION_TOKEN       # Optional
SUPABASE_URL       # Optional
SUPABASE_KEY       # Optional
OPENAI_API_KEY     # Optional
```

`GITHUB_TOKEN` is automatically provided by GitHub Actions.

## Auto-approve philosophy

This system is designed to **never ask for confirmation**. Every P0 is logged and issued. Every P1/P2 that can be fixed in code is fixed in code. Only credential rotation (P0-security) requires a human because no system should auto-rotate secrets it can't verify.

## Logs

Audit logs: `audit_log/run_YYYY-MM-DD.json`  
Action queues: `action_queue/queue_YYYY-MM-DD.json`  
Findings: `findings/`
