from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROLES = ROOT / "config" / "operator_administration_roles.v1.json"
SPECIALISTS = ROOT / "config" / "operator_administration_specialists.v1.json"
GENOME_SQL = ROOT / "supabase" / "migrations" / "20260920011000_operator_administration_genome_v1.sql"
ROLES_SQL = ROOT / "supabase" / "migrations" / "20260920013000_operator_administration_roles_v1.sql"
SPECIALISTS_SQL = ROOT / "supabase" / "migrations" / "20260920021000_operator_administration_specialists_v1.sql"


def test_operator_administration_registries_are_source_readable() -> None:
    roles = json.loads(ROLES.read_text())
    specialists = json.loads(SPECIALISTS.read_text())

    assert roles["schema"] == "glaciereq.operator-role-registry.v1"
    assert len(roles["roles"]) == 53
    assert specialists["schema"] == "glaciereq.operator-specialist-cohort.v1"
    assert specialists["authority_holder"] == "OPERATOR"
    assert len(specialists["agents"]) == 18


def test_operator_administration_migration_chain_is_complete() -> None:
    assert GENOME_SQL.exists()
    assert ROLES_SQL.exists()
    assert SPECIALISTS_SQL.exists()


def test_role_assignment_requires_explicit_attribution_and_hashes_payload() -> None:
    sql = SPECIALISTS_SQL.read_text()

    assert "create or replace function public.oa_assign_role_v1(" in sql
    assert "p_assigned_by text default null" in sql
    assert "assigned_by identity is required" in sql
    assert "v_source_class := public.oa_source_class_v1(p_assigned_by)" in sql
    assert "digest(" in sql
    assert "sha256" in sql
    assert "security definer" in sql.lower()


def test_specialist_genome_preserves_operator_rooted_authority() -> None:
    sql = SPECIALISTS_SQL.read_text()

    assert "'authority_holder','OPERATOR'" in sql
    assert "'role_does_not_create_authority',true" in sql
    assert "'no_silent_scope_expansion',true" in sql
    assert "'replacement_executor_must_rehydrate',true" in sql
