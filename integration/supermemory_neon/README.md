# Supermemory + Neon Integration — apex-control-plane

This directory wires the daily audit loop and connector registry into Supermemory (semantic memory) and Neon (operational state).

## Role in the Stack

apex-control-plane is the **daily audit and connector lifecycle layer**. It:
- Polls registered connectors for health + activity
- Pushes summarized connector status into Supermemory for agent recall
- Writes precise audit records to Neon for reporting and replication

## Files

| File | Purpose |
|------|---------|
| `connector_registry.py` | CRUD for connector records in Neon |
| `audit_loop.py` | Daily audit runner — checks health, pushes summaries to Supermemory |
| `memory.py` | Shared Supermemory client (mirrors Pro-DOCTOR-STRANGE version) |
| `migrations/001_connectors.sql` | Neon schema for connectors + audit_runs |
| `.env.example` | Required env vars |

## Container Tag Conventions

| Tag | Populated By | Consumed By |
|-----|-------------|-------------|
| `connector:{connectorId}` | audit_loop.py | agents querying connector status |
| `audit:daily:{date}` | audit_loop.py | orchestrator daily summaries |
