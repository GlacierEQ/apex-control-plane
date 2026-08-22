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

### Connector Bridge Rules

1. Session-level OAuth credentials, API keys, cookies, and temporary download URLs remain outside this repository.
2. APEX admits connector results only through the versioned receipt contract in `config/apex_connector_catalog.json`.
3. A successful provider probe or read receipt does not authorize an external write.
4. Every external write requires an active catalog operation, an exact approval record naming target and consequence, and a resulting provider execution receipt.
5. Scheduled connector writes remain disabled unless the user approves a reviewed workflow specifically for that operation.

### If a Secret Is Exposed

1. Preserve the original evidence location and record the exposure without reproducing the secret in tickets, logs, or new commits.
2. Revoke or rotate the credential at the provider as soon as operationally feasible.
3. Replace any active credential through the relevant protected secret store, never a tracked source file.
4. Assess the affected systems, access scope, and audit history before deciding whether any repository history change is warranted.
5. Do not rewrite history, force-push, delete branches, or purge evidence without the user’s explicit approval and a stated preservation consequence.
6. Record the incident in an access-controlled security log with secret-free provenance references.

### Reporting

Report security issues to: GLACIER.EQUILIBRIUM@GMAIL.COM
