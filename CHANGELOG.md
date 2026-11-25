# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-11-18

### Added
- Connector receipt bridge registry for the APEX control plane (`5158455`).
- Full APEX autonomous daily audit system: audit loop, connector registry,
  security hardening, CI/CD scheduler, and action queue.
- Durable mission lifecycle and mission-resume contracts gated on applied context.

### Changed
- Require applied context (not hydration) for cursor-only mission resumption and
  for overhaul completion; recovered connector dispatch now regresses correctly
  on fact-key-aware dispatch and denies missing keys.
- Require proven context application before certifying overhaul completion;
  corrected connector dashboard counts to source-verified provider completions.
- Guard APEX bundle closure against unevidenced item completion; reject empty
  receipt configuration and malformed provider readback as verified execution.
- Rank scoped memory retrieval by relevance before authority ties; align native
  context authority classes with enforced source statuses.

### Fixed
- Prevent recrediting identical native outcomes across workers (reward-replay
  idempotence); a durable model commit now precedes the success reward log so a
  failed checkpoint cannot train the model or create a false reward log.
- Close five meeting-intelligence RLS-bypass read paths and the APEX connector
  dashboard RLS bypass for authenticated users; removed residual privileged
  meeting cohort views flagged by the security advisor.
- Restrict unauthenticated privileged health-write RPC and remove remaining public
  execution of privileged internal RPC writers.
- Prevent NULL-scope retrieval from mixing legal cases; prevent unrelated
  high-authority context injection; preserve the native SQL fallback deployed for
  402-restricted compiler.
- Prevent direct parent invocation false completion on the hourly overhaul;
  persist live hourly-overhaul completion rejection and native test receipt.
- GitHub execution CLI now retries only after a native readback establishes the
  missing effect; transient provider PUT recovers without duplicate remote write.
- Terminate SQL function before privilege statements; keep vendor sitemap crawl
  below source-bearing operator memories.
- Documented the VillAIge host boundary in the README.

### Security
- Multiple RLS-bypass and privileged-RPC exposure paths closed (see Fixed).
- Provenance does not reduce scope: recovered connector work continues across
  localized blockers without weakening authorization checks.

[3.0.0]: https://github.com/GlacierEQ/apex-control-plane/compare/2.0.0...3.0.0