# Unified CASEBRAIN Control Plane

## Scope

This repository hosts the bounded runtime control plane for the CASEBRAIN federation.
AKOS remains governance canon. Original evidence remains in its source system.
Supermemory stores distilled routing and provenance pointers, not raw evidence or secrets.

## Runtime pipeline

```text
Source Event
  -> canonical normalization
  -> SHA-256 + immutable envelope
  -> claim-class boundary check
  -> timeline/deadline projection
  -> analytical threat signals
  -> deterministic recommendations
  -> hard human gate
  -> immutable receipt
  -> optional reviewed projection adapters
```

## Four brains, one control plane

1. **Upload Intelligence** — dedupe by canonical hash, preserve source URI, classify sensitivity, and reject secret-bearing payloads.
2. **Timeline Brain** — order events, compute deadline distance, preserve whether each deadline is confirmed.
3. **Threat Intelligence Hub** — produce analytical signals only; retain alternative explanations and deny external action.
4. **Autonomous Decision Engine** — recommend review steps, evidence checks, sequencing, and preparation; never file, contact, publish, or promote facts autonomously.

## Claim boundary

Every item is exactly one of:

- `verified_fact`
- `allegation`
- `model_inference`
- `recommendation`

No component may silently promote between classes.

## Self-healing behavior

The control plane includes bounded exponential retry, per-connector circuit breakers,
dead-letter capture, idempotent event processing, deterministic hashing, and append-only
receipts. “Self-healing” means recoverable transport behavior—not autonomous changes to
case facts, evidence, legal strategy, or external systems.

## Secret handling

The exposed Supermemory credential and tokenized webhook URL must be rotated. This build
uses only environment-variable names and secret-manager references. No raw secret is
embedded in code, logs, memory, documentation, or test fixtures.

## First verification slice

1. Rotate exposed credentials.
2. Select one non-sensitive primary record.
3. Compute a full SHA-256 locally.
4. Create one `CaseEvent` with stable source pointers.
5. Run `CaseBrainOrchestrator.process_event` in read-only mode.
6. Validate output hashes and append the receipt.
7. Store only the reviewed distilled summary/provenance pointer in Supermemory.
8. Promote no connector or worker to `verified_live` until the dated receipt is reviewed.
