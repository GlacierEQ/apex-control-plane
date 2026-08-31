# LangGraph + Supabase Impact-Weighted Runtime

## Architecture

**LangGraph = flow and resumable orchestration.**  
**Supabase = durable state spine.**  
**Local startup projection = immediate tunnel context.**

Do not make Supabase or LangGraph an authority over the Operator. They persist and route state.

### Startup path

1. Python imports `sitecustomize.py`.
2. `sitecustomize.py` imports `operator_impact_context.py`.
3. Local impact profile is available immediately with no network dependency.
4. Existing APEX strong boot continues.
5. Authorized workers may refresh the profile from Supabase `operator-impact-context`.
6. Material context changes emit structured events/checkpoints to `operator_decision_events_v1`.

### LangGraph path

Use LangGraph when the workflow benefits from:
- durable execution;
- resumability after failure;
- explicit state transitions;
- long-running cases or engineering jobs;
- human intervention;
- time-travel/replay;
- cross-step memory.

Use a Postgres-backed LangGraph checkpointer against Supabase Postgres for production state. Keep LangGraph checkpoint tables separate from legal evidence/source-of-truth tables.

### Supabase roles

- `operator_decision_runtime_v1`: operator interpretation profile.
- `operator_runtime_context_current_v1`: stable read model.
- `operator_decision_events_v1`: append-only decision checkpoints/outcomes.
- `operator-impact-context`: JWT-protected distribution endpoint.
- existing connector/runtime tables: routing, health, receipts, case state.

### Guardrail

A missing Supabase connection must not erase the impact-first mentality. Startup falls back to the local projection. Supabase refresh improves currency; it does not grant permission to think.
