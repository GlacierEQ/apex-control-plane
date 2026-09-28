# Audit Logs

Append-only evidence ledger for all APEX daily audit runs.

## Format

Each file is newline-delimited JSON (`.jsonl`). Each line is one complete audit run:

```json
{
  "run_timestamp": "2026-05-27T16:00:00Z",
  "operator": "GlacierEQ",
  "finding_count": 4,
  "p0_count": 0,
  "p1_count": 2,
  "findings": [...],
  "action_queue": {...}
}
```

## Retention

- Files kept for 90 days via GitHub Actions artifact retention
- For legal/forensic use: export to Supabase or Notion for permanent storage

## Note

The `.jsonl` log files are gitignored to prevent repo bloat. They are available as GitHub Actions artifacts after each run.
