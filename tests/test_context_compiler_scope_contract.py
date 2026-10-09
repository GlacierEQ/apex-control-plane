"""Context Compiler purpose must not narrow mission or rewrite historical migration."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/operator_administration_roles.v1.json"
MIGRATION = ROOT / "supabase/migrations/20261009190000_context_compiler_full_mission_scope.sql"


def test_context_compiler_contract_keeps_mission_and_provider_evidence():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    role = next(r for r in data["roles"] if r["role_key"] == "OA.ROLE.CONTEXT_COMPILER")
    assert "complete mission-preserving" in role["purpose"]
    assert "omit consequential evidence or capabilities" in role["purpose"]
    assert "smallest sufficient" not in role["purpose"].lower()
    assert "relevant current instructions" in role["win_condition"]


def test_forward_migration_is_guarded_not_a_historical_seed_rewrite():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "where role_key = 'OA.ROLE.CONTEXT_COMPILER'" in sql
    assert "and purpose = 'Compile the smallest sufficient authority-aware context package before execution.'" in sql
    assert "complete mission-preserving" in sql
    assert "update public.oa_roles_v1" in sql
    assert "delete from" not in sql.lower()
