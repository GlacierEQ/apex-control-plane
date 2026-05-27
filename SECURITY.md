# Security Policy — APEX Control Plane

## ⚠️ ZERO HARDCODED SECRETS

This repository and ALL repos under GlacierEQ operate under a strict zero-hardcoded-secret policy.

### Credential Rules

1. **Never** commit API keys, tokens, passwords, or connection strings to source code
2. **Never** include secrets in README files, comments, or documentation
3. **Never** store secrets in JSON config files tracked by git
4. All secrets live in **GitHub Secrets** (for CI/CD) or **.env files** (gitignored locally)
5. Any exposed secret must be **revoked immediately** before any other action

### Secret Storage Hierarchy

```
Production:  GitHub Repository Secrets → GITHUB_TOKEN, NOTION_TOKEN, etc.
Local:       .env file (never committed, listed in .gitignore)
CI/CD:       ${{ secrets.SECRET_NAME }} in workflow YAML only
```

### Required .gitignore entries (all repos)

```
.env
.env.*
*.env
secrets.json
credentials.json
*_credentials.*
*_secrets.*
```

### If a Secret Is Exposed

1. Revoke the credential at the provider immediately
2. Generate new credential
3. Add to GitHub Secrets only
4. Purge from git history: `git filter-repo --path-glob '*.env' --invert-paths`
5. Force push and notify all collaborators
6. Log incident in `audit_logs/security_incidents.jsonl`

### Reporting

Report security issues to: GLACIER.EQUILIBRIUM@GMAIL.COM
