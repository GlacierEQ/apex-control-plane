# APEX Control Plane

> Sovereign operator system for GlacierEQ — daily audit, connector registry, security hardening, action queue.

## What this does

- Validates all connectors (GitHub, Notion, Supabase, Redis) daily
- Scans for secret leakage and endpoint drift
- Ranks findings by severity (P0–P3)
- Writes an append-only audit log to `apex_control_plane.json`
- Commits evidence automatically via GitHub Actions
- Emits a prioritized action queue every run

## Quick start

```bash
# Install (no dependencies — stdlib only)
python apex_daily.py
```

## Secrets setup (required)

Go to: **Settings → Secrets and variables → Actions**

| Secret name | Value |
|---|---|
| `APEX_GITHUB_TOKEN` | GitHub PAT (repo + read:user scopes) |
| `APEX_NOTION_TOKEN` | Notion integration token |
| `APEX_SUPABASE_KEY` | Supabase service role key (optional) |

**Never** hardcode tokens in source. All secrets are read from environment variables only.

## Schedule

Runs daily at 8:00 AM UTC (10:00 PM HST) via `.github/workflows/apex-daily.yml`.
Manual trigger available anytime via `workflow_dispatch`.

## Connector states

| State | Meaning |
|---|---|
| `declared` | Defined in registry, not yet tested |
| `authenticated` | Token present and valid |
| `reachable` | API endpoint responding |
| `action_capable` | All checks pass — safe to use |

## Reality firewall

Before adding any new connector or capability:
- [ ] Can I authenticate right now with a real token?
- [ ] Is there a public API doc URL?
- [ ] Does a test call return 200?
- [ ] Is the secret in env (not source)?

If any box is unchecked → status = `blocked`

## Files

```
apex-control-plane/
├── apex_daily.py              # Daily audit runner
├── apex_control_plane.json    # Control plane state + audit log
├── connectors/
│   ├── github_validator.py    # GitHub connector
│   ├── notion_validator.py    # Notion connector
│   ├── supabase_validator.py  # Supabase connector
│   └── redis_validator.py     # Redis connector
├── .github/
│   └── workflows/
│       └── apex-daily.yml     # Daily CI scheduler
└── SECURITY.md                # Security policy
```
