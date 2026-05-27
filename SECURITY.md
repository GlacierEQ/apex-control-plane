# Security Policy

## Credential rules (non-negotiable)

1. **No secrets in source** — all tokens live in environment variables or GitHub Secrets only
2. **No secrets in chat** — never paste a live token into any chat, doc, or issue
3. **Rotation cadence** — rotate all tokens every 90 days or immediately on any suspected exposure
4. **Minimum scopes** — GitHub PAT: `repo` + `read:user` only. Notion: integration token scoped to relevant pages only
5. **Audit log is append-only** — never delete or modify past audit entries

## If a secret is exposed

1. Revoke it immediately at the provider (GitHub, Notion, Supabase)
2. Generate a new one
3. Update the GitHub Secret
4. Open a P0 finding in the audit log
5. Search the entire repo history: `git log -p | grep -i token`

## Reporting

Open a private issue in this repo. Do not post credentials publicly.
