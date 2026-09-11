from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARDENING = ROOT / "db/migrations/20260909_control_plane_awareness_function_search_path_hardening_v2_3.sql"


def test_awareness_helpers_pin_search_path() -> None:
    sql = HARDENING.read_text(encoding="utf-8")
    assert "control_plane_normalize_awareness_text_v2" in sql
    assert "control_plane_action_target_matches_v2" in sql
    assert sql.count("set search_path='pg_catalog','public'") == 2
