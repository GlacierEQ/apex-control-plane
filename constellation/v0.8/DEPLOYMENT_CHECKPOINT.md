# Constellation Core v0.8 — Deployment Checkpoint

Status: GitHub deployment tracking initialized.

## Live tracking issue

- Repo: `GlacierEQ/apex-control-plane`
- Issue: `#2`
- Purpose: deploy Constellation Core v0.8 Agent Gatling.

## Generated artifacts

- `constellation-core-bootstrap-v0.8.zip`
  - SHA-256: `a13485d3063380a0aa81c7ad9cc77d703915f5b7bcafe56a6c063d501bcfacc4`
  - Contents: 163 files.

- `constellation-deployment-kit-v0.8.zip`
  - SHA-256: `fa01728d2eabcc1a2f555fa59f2ac09cbf719783a4e04a3917bfcb42864784c6`

## Intended branch

`feature/constellation-core-v0.8-agent-gatling`

## Local import command

```bash
./import_constellation_core.sh \
  /path/to/constellation-core-bootstrap-v0.8.zip \
  /path/to/aspen-grove-operator-v7 \
  feature/constellation-core-v0.8-agent-gatling

git push -u origin feature/constellation-core-v0.8-agent-gatling
```

## Validation sequence

```bash
npm install
npm run test:schemas
npm run typecheck
npm run demo:gatling
npm run demo:gatling:salvo
npm run demo:gatling:registry
npm run demo:gatling:lane
npm run demo:gatling:report
```

## Connector limitation observed

The available Zapier GitHub file action accepts content inside nested action parameters. The sandbox file path could not be rewritten as a GitHub file payload from that nested field, so the full zip could not be safely committed directly through the connector in this session.

## Priority lock

Deploy v0.8 → run Agent Gatling dry-run → promote P0 Job Acquisition salvo.
