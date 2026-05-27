# APEX Control Plane

**Sovereign operator system for GlacierEQ — autonomous daily audit, connector registry, security hardening, and action queue.**

## What this does

- Runs every day at 8 AM HST automatically via GitHub Actions
- Validates all connectors (GitHub, Notion, and more)
- Scans repos for health issues, open issue drift, and fragmentation
- Ranks all findings by severity (P0 → P3)
- Emits a prioritized action queue
- Commits findings to `apex_control_plane.json` as a tamper-evident audit log
- Auto-creates GitHub issues for any P0 critical findings

## Zero-approval operation

The workflow runs fully autonomously. No human needs to press go.

```
Schedule: daily 8:00 AM HST
Trigger: also fires on every push to main
Auto-commit: yes — audit log written back to repo
P0 escalation: auto-creates GitHub issue with full evidence
```

## Setup (one-time)

1. Go to repo **Settings → Secrets → Actions**
2. Add `APEX_GITHUB_TOKEN` — your GitHub PAT with `repo` scope
3. Add `APEX_NOTION_TOKEN` — your Notion integration token
4. Push any change to `main` to trigger the first run immediately

## Files

| File | Purpose |
|---|---|
| `apex_daily.py` | Core audit runner — connector validation, repo scan, finding ranking |
| `apex_control_plane.json` | Live registry — connector states, findings, audit log |
| `.github/workflows/apex-daily.yml` | Scheduler + auto-commit + P0 escalation |

## Severity levels

| Level | Meaning | Auto-action |
|---|---|---|
| P0 | Critical — broken auth, exposed secrets | Creates GitHub issue immediately |
| P1 | High — connectivity failure, token expired | Added to immediate queue |
| P2 | Medium — repo drift, stale issues | Added to strategic queue |
| P3 | Low — hygiene, archiving | Added to blocked queue |

## Expanding connectors

Add a new `validate_X()` function in `apex_daily.py` following the same pattern as `validate_github()` and `validate_notion()`. The system picks it up automatically on the next run.
