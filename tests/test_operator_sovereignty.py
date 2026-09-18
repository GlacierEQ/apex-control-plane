from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "supabase" / "functions" / "apex-connector-tool-gateway" / "index.ts"
CATALOG = ROOT / "config" / "apex_connector_catalog.json"
MIGRATIONS = ROOT / "db" / "migrations"


def test_gateway_does_not_promote_every_mutation_to_approval_required():
    source = GATEWAY.read_text(encoding="utf-8")
    legacy = 'route.mutation_class !== "read" || route.approval_required === true'

    assert legacy not in source
    assert 'const approvalRequired = route.approval_required === true;' in source
    assert '"active_mission_authority"' in source
    assert '"scoped_consequence_authority"' in source


def test_catalog_encodes_operator_sovereignty_without_dropping_system_controls():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    security = catalog["security"]

    assert security["external_write_requires_exact_approval"] is False
    assert security["recoverable_write_inherits_mission_authority"] is True
    assert security["consequence_sensitive_write_requires_scoped_authority"] is True
    assert security["bridge_receipt_required"] is True

    for connector in catalog["connectors"].values():
        for rule in connector["write_operations"].values():
            assert isinstance(rule["approval_required"], bool)
            assert rule["idempotency_required"] is True
            assert rule["terminal_readback_required"] is True


def test_authority_migration_removes_blanket_write_coercion_and_stale_probe_gate():
    migration = (
        MIGRATIONS / "20260913233000_operator_sovereignty_authority_semantics.sql"
    ).read_text(encoding="utf-8")

    assert "drop constraint if exists connector_route_policy_v3_mutation_approval_guard" in migration
    assert "(p_approval_required or v_policy.approval_required)" in migration
    assert "mutation_class in ('write','destructive')" not in migration
    assert "connector_probe_stale_or_missing" not in migration
    assert "Health and probe freshness are observability signals, not permission gates" in migration
