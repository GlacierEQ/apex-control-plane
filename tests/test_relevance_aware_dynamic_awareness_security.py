from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "db/migrations/20260909_control_plane_relevance_aware_awareness_v2_1.sql"
HARDENING = ROOT / "db/migrations/20260911151918_harden_relevance_aware_awareness_v2_4.sql"


def test_awareness_helpers_pin_search_path() -> None:
    base = BASE.read_text(encoding="utf-8")
    hardening = HARDENING.read_text(encoding="utf-8")
    assert "control_plane_normalize_awareness_text_v2" in base
    assert "control_plane_action_target_matches_v2" in base
    assert base.count("set search_path='pg_catalog','public'") >= 2
    assert "set search_path='pg_catalog','public'" in hardening
