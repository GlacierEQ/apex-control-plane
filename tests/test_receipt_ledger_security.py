from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEDERATED = ROOT / "db/migrations/20260911151025_federated_execution_permit_service_role_least_privilege_v1.sql"
INGEST = ROOT / "db/migrations/20260911151307_harden_continuity_ingest_processing_receipts_append_only_v1.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_federated_permit_service_role_has_only_required_table_privileges() -> None:
    sql = _sql(FEDERATED)
    assert "revoke all on table public.continuity_federated_execution_permits_v1 from service_role" in sql
    assert "revoke all on table public.continuity_federated_execution_permit_receipts_v1 from service_role" in sql
    assert "grant select, insert on table public.continuity_federated_execution_permits_v1 to service_role" in sql
    assert "grant select, insert on table public.continuity_federated_execution_permit_receipts_v1 to service_role" in sql
    assert "grant delete" not in sql
    assert "grant update" not in sql
    assert "grant truncate" not in sql


def test_ingest_receipts_are_directly_read_only_for_service_role() -> None:
    sql = _sql(INGEST)
    assert "revoke all on table public.continuity_ingest_processing_receipts_v1 from service_role" in sql
    assert "grant select on table public.continuity_ingest_processing_receipts_v1 to service_role" in sql
    assert "grant insert" not in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql
    assert "grant truncate" not in sql


def test_ingest_receipts_enforce_append_only_and_explicit_client_deny() -> None:
    sql = _sql(INGEST)
    assert "continuity_ingest_processing_receipts_append_only_v1" in sql
    assert "before update or delete on public.continuity_ingest_processing_receipts_v1" in sql
    assert "continuity_ingest_processing_receipts_v1 is append-only" in sql
    assert "continuity_ingest_processing_receipts_client_deny_v1" in sql
    assert "to anon, authenticated" in sql
    assert "using (false)" in sql
    assert "with check (false)" in sql
