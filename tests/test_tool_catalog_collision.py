"""Regression tests for catalog capability selection."""
import pytest
from src.tool_catalog import CatalogEntry, select, hot_swap


def entry(name, kind):
    return CatalogEntry(name=name, kind=kind, description="", path=f"/{kind}/{name}")


def test_collision_requires_qualification():
    catalog = [entry("shared", "skill"), entry("shared", "connector")]
    with pytest.raises(ValueError, match="ambiguous"):
        select(catalog, ["shared"])
    assert select(catalog, ["skill:shared"]) == [catalog[0]]
    assert hot_swap([], catalog, ["connector:shared"]) == [catalog[1]]


def test_unique_legacy_name_and_unknown_remain_supported():
    catalog = [entry("unique", "skill")]
    assert select(catalog, ["unique", "missing"]) == catalog
    assert select(catalog, ["connector:unique"]) == []


def test_duplicate_same_kind_fails_closed():
    catalog = [entry("same", "connector"), entry("same", "connector")]
    with pytest.raises(ValueError, match="ambiguous"):
        select(catalog, ["connector:same"])


def test_repeated_bare_and_qualified_requests_load_once_in_first_seen_order():
    catalog = [entry("alpha", "skill"), entry("beta", "connector")]
    assert select(catalog, ["alpha", "skill:alpha", "beta", "connector:beta", "alpha"]) == catalog
    assert hot_swap([], catalog, ["connector:beta", "beta", "alpha"]) == [catalog[1], catalog[0]]


def test_literal_colon_name_is_selectable_without_guessing():
    catalog = [entry("region:west", "skill")]
    assert select(catalog, ["region:west"]) == catalog
    assert select(catalog, ["skill:region:west"]) == catalog


def test_literal_name_and_qualified_name_collision_fails_closed():
    catalog = [entry("skill:shared", "connector"), entry("shared", "skill")]
    with pytest.raises(ValueError, match="ambiguous"):
        select(catalog, ["skill:shared"])
    assert select(catalog, ["connector:skill:shared"]) == [catalog[0]]


def test_content_loading_requires_explicit_selection(tmp_path, capsys):
    from src.tool_catalog import main
    root = tmp_path / "skills"
    doc = root / "private" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("private capability content", encoding="utf-8")
    assert main(["--skills", str(root), "--load-content"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--select" in captured.err
    assert main(["--skills", str(root), "--select", "skill:private", "--load-content"]) == 0
    assert "private capability content" in capsys.readouterr().out
