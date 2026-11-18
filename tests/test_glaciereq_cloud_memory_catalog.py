"""Cross-cloud source catalog tests: native IDs, privacy and APEX causal retrieval."""
from copy import deepcopy
import pytest
from src.glaciereq_cloud_memory_catalog import prepare_catalog, select_project_sources, provider_parent_rows
from src.glaciereq_memory_graph_recovery import recover, compose_admission_instruction


OBSERVED = "2026-11-18T16:45:00Z"


def file(provider="google_drive", **updates):
    row = {
        "provider": provider,
        "account_id": "account-a",
        "item_id": "native-file-123",
        "name": "Constellation Memory Integration.md",
        "url": "https://drive.google.com/file/d/native-file-123/view",
        "modified_at": "2026-10-31T15:38:43Z",
        "mime_type": "text/markdown",
        "size": 1352,
        "classification": "internal_metadata_no_case_payload",
        "related_projects": ["APEX", "CONSTELLATION"],
    }
    row.update(updates)
    return row


def graph():
    def node(key, kind, parent, **meta):
        return {"source_id": "GLACIEREQ-MEMGRAPH-V1-" + key, "memory_type": "structured_memory_graph_node",
                "metadata": {"graph_id": "GLACIEREQ-MEMGRAPH-V1", "node_key": key, "node_kind": kind,
                             "parent_key": parent, **meta}}
    return [node("ROOT", "mission", None), node("APEX", "project", "ROOT"),
            node("OMNI", "project", "ROOT"),
            node("DRIVE-CATALOG", "project", "ROOT"),
            node("APEX-CURSOR", "cursor", "APEX", next_transition="authenticated_graph_retrieval")]


def test_stable_identity_and_pointer_only():
    a = prepare_catalog([file()], observed_at=OBSERVED)
    b = prepare_catalog([file()], observed_at=OBSERVED)
    assert a == b
    item = a[0]
    assert item["memory_type"] == "structured_memory_graph_node"
    assert item["metadata"]["parent_key"] == "DRIVE-CATALOG"
    assert item["metadata"]["node_kind"] == "cloud_file"
    assert item["metadata"]["related_projects"] == ["APEX", "CONSTELLATION"]
    assert item["source_hash"] is None
    assert "contents" not in item["metadata"]
    assert "next_cursor" not in item["metadata"]
    assert item["court_facing"] is False


def test_account_and_provider_id_are_part_of_identity():
    a = prepare_catalog([file()], observed_at=OBSERVED)[0]["id"]
    b = prepare_catalog([file(account_id="account-b")], observed_at=OBSERVED)[0]["id"]
    c = prepare_catalog([file(provider="onedrive", url="https://onedrive.live.com/?id=abc")], observed_at=OBSERVED)[0]["id"]
    assert len({a, b, c}) == 3


def test_idempotent_duplicate_and_conflicting_revision_rejected():
    a = file()
    assert len(prepare_catalog([a, deepcopy(a)], observed_at=OBSERVED)) == 1
    with pytest.raises(ValueError, match="conflicting"):
        prepare_catalog([a, file(modified_at="2026-11-01T00:00:00Z")], observed_at=OBSERVED)


def test_provider_parents_are_stable_and_no_duplicate_drive_root():
    roots = provider_parent_rows(observed_at=OBSERVED)
    assert {x["metadata"]["node_key"] for x in roots} == {"CLOUD-DROPBOX", "CLOUD-ONEDRIVE"}
    assert all(x["metadata"]["parent_key"] == "ROOT" for x in roots)


def test_dropbox_native_namespace_without_fabricated_link():
    item = file("dropbox", url=None, item_id="id:AbCd_09", name="AI Operator Code Development.pdf",
                namespace_path="ns:12534579985//AI Operator Code Development.pdf",
                classification="restricted_pointer_only", related_projects=["ASPEN"])
    row = prepare_catalog([item], observed_at=OBSERVED)[0]
    assert row["source_uri"] is None
    assert row["metadata"]["provider_path"].startswith("ns:")
    assert row["metadata"]["parent_key"] == "CLOUD-DROPBOX"


def test_rejects_foreign_urls_and_raw_content_fields():
    with pytest.raises(ValueError, match="provider URL"):
        prepare_catalog([file(url="https://evil.example/file")], observed_at=OBSERVED)
    with pytest.raises(ValueError, match="raw content"):
        prepare_catalog([file(transcript="fabricated speech")], observed_at=OBSERVED)


def test_rejects_invalid_timestamps_and_case_leakage():
    with pytest.raises(ValueError, match="timestamp"):
        prepare_catalog([file(modified_at="2026-11-18")], observed_at=OBSERVED)
    with pytest.raises(ValueError, match="classification"):
        prepare_catalog([file(classification="public_verified_fact")], observed_at=OBSERVED)


def test_select_by_related_project_without_sensitive_cross_leak():
    technical = prepare_catalog([file()], observed_at=OBSERVED)[0]
    restricted = prepare_catalog([file("onedrive", url="https://onedrive.live.com/?id=abc", account_id="one",
                                        item_id="file-456", classification="restricted_pointer_only",
                                        related_projects=["APEX"])], observed_at=OBSERVED)[0]
    rows = graph() + provider_parent_rows(observed_at=OBSERVED) + [technical, restricted]
    sources = select_project_sources(rows, "APEX")
    assert len(sources) == 1 and sources[0]["source_id"] == technical["source_id"]
    assert select_project_sources(rows, "OMNI") == []
    assert len(select_project_sources(rows, "APEX", include_restricted=True)) == 2


def test_apex_recovery_includes_bound_cloud_sources_without_changing_cursor():
    cloud = prepare_catalog([file()], observed_at=OBSERVED)[0]
    rows = graph() + [cloud]
    selected = recover(rows, "APEX")
    assert selected["next_cursor"] == "authenticated_graph_retrieval"
    assert selected["cloud_sources"][0]["source_id"] == cloud["source_id"]
    note = compose_admission_instruction("mission", "hmac-journal", "trusted_cursor", selected)
    assert "trusted_cursor" in note
    assert cloud["source_id"] in note
    assert "UNTRUSTED" in note
