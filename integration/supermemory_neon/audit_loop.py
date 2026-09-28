"""
Daily audit loop for apex-control-plane.

Runs on a schedule (cron or process manager):
  python audit_loop.py

For each active connector:
  1. Calls its health check endpoint or ping.
  2. Records result in Neon.
  3. Pushes human-readable summary to Supermemory.

At the end of the run, pushes a daily audit summary to Supermemory.
"""

import os
import json
from datetime import datetime, timezone
from connector_registry import ConnectorRegistry
from memory import push_connector_summary, push_audit_summary


def check_connector_health(connector: dict) -> dict:
    """
    Stub health check — replace with actual ping logic per connector kind.
    Supported kinds: github, notion, supabase, sentry, neon, supermemory, clickup
    """
    kind = connector.get("kind", "unknown")
    name = connector["name"]
    config = connector.get("config", {})
    if isinstance(config, str):
        config = json.loads(config)

    # Extend with real HTTP health checks per kind
    health_checks = {
        "github":      lambda c: {"ok": True, "note": "API token present"} if c.get("token") else {"ok": False, "note": "missing token"},
        "notion":      lambda c: {"ok": True, "note": "integration key present"} if c.get("api_key") else {"ok": False, "note": "missing api_key"},
        "supabase":    lambda c: {"ok": True, "note": "url+key present"} if c.get("url") and c.get("service_key") else {"ok": False, "note": "missing url or service_key"},
        "sentry":      lambda c: {"ok": True, "note": "dsn present"} if c.get("dsn") else {"ok": False, "note": "missing dsn"},
        "neon":        lambda c: {"ok": True, "note": "dsn present"} if c.get("dsn") else {"ok": False, "note": "missing dsn"},
        "supermemory": lambda c: {"ok": True, "note": "api_key present"} if c.get("api_key") else {"ok": False, "note": "missing api_key"},
        "clickup":     lambda c: {"ok": True, "note": "api_key present"} if c.get("api_key") else {"ok": False, "note": "missing api_key"},
        "pinecone":    lambda c: {"ok": True, "note": "api_key present"} if c.get("api_key") else {"ok": False, "note": "missing api_key"},
        "qdrant":      lambda c: {"ok": True, "note": "url present"} if c.get("url") else {"ok": False, "note": "missing url"},
        "motherduck":  lambda c: {"ok": True, "note": "token present"} if c.get("token") else {"ok": False, "note": "missing token"},
    }
    check_fn = health_checks.get(kind, lambda c: {"ok": True, "note": "no health check defined"})
    result = check_fn(config)
    result["connector_name"] = name
    result["kind"] = kind
    return result


def run_audit():
    registry = ConnectorRegistry()
    connectors = registry.list_active()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = []

    print(f"[audit] Starting daily audit for {date_str} — {len(connectors)} connectors")

    for connector in connectors:
        conn_id = str(connector["id"])
        name = connector["name"]
        kind = connector["kind"]

        health = check_connector_health(connector)
        status = "healthy" if health["ok"] else "degraded"

        registry.record_health(conn_id, status, health)

        summary = (
            f"Connector: {name} ({kind})\n"
            f"Status: {status}\n"
            f"Note: {health.get('note', '')}\n"
            f"Checked: {date_str}"
        )
        push_connector_summary(conn_id, summary)

        results.append({"name": name, "kind": kind, "status": status})
        print(f"  [{status.upper()}] {name} ({kind})")

    healthy = sum(1 for r in results if r["status"] == "healthy")
    degraded = len(results) - healthy

    daily_summary = (
        f"Daily Audit — {date_str}\n"
        f"Total connectors: {len(results)}\n"
        f"Healthy: {healthy}\n"
        f"Degraded: {degraded}\n\n"
        + "\n".join(f"- {r['name']} ({r['kind']}): {r['status']}" for r in results)
    )
    push_audit_summary(date_str, daily_summary)
    print(f"[audit] Complete — {healthy}/{len(results)} healthy")


if __name__ == "__main__":
    run_audit()
