"""Tests for the tool catalog. Every number here comes from a run."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tool_catalog import (
    build_catalog,
    hot_swap,
    menu,
    search_catalog,
    select,
)


def _write_doc(path: Path, title: str, bullet: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n- {bullet}\n", encoding="utf-8")


def _fixture_catalog(tmp_path: Path):
    skills = tmp_path / "skills"
    connectors = tmp_path / "connectors"
    _write_doc(skills / "shopping" / "SKILL.md", "Shopping", "Find products and compare prices.")
    _write_doc(skills / "groceries" / "SKILL.md", "Groceries", "Shop for groceries for delivery.")
    _write_doc(connectors / "gmail" / "CONNECTOR.md", "Gmail", "Search, read and send Gmail.")
    _write_doc(connectors / "github" / "CONNECTOR.md", "GitHub", "Work with repositories.")
    return build_catalog([skills], [connectors])


def test_catalog_lists_everything_found(tmp_path):
    catalog = _fixture_catalog(tmp_path)
    assert {e.name for e in catalog} == {"shopping", "groceries", "gmail", "github"}
    kinds = {e.name: e.kind for e in catalog}
    assert kinds["shopping"] == "skill"
    assert kinds["gmail"] == "connector"
    descriptions = {e.name: e.description for e in catalog}
    assert descriptions["shopping"] == "Find products and compare prices."
    assert descriptions["gmail"] == "Search, read and send Gmail."


def test_menu_shows_every_entry_one_line(tmp_path):
    catalog = _fixture_catalog(tmp_path)
    lines = menu(catalog)
    assert len(lines) == len(catalog) == 4
    joined = "\n".join(lines)
    for name in ("shopping", "groceries", "gmail", "github"):
        assert name in joined


def test_search_returns_all_matches_no_cap(tmp_path):
    catalog = _fixture_catalog(tmp_path)
    hits = search_catalog(catalog, "shop")
    assert {e.name for e in hits} == {"shopping", "groceries"}
    assert search_catalog(catalog, "") == []


def test_select_loads_only_what_was_picked(tmp_path):
    catalog = _fixture_catalog(tmp_path)
    loaded = select(catalog, ["gmail"])
    assert [e.name for e in loaded] == ["gmail"]
    assert select(catalog, []) == []


def test_select_unknown_name_returns_nothing(tmp_path):
    catalog = _fixture_catalog(tmp_path)
    assert select(catalog, ["no-such-tool"]) == []


def test_hot_swap_replaces_loaded_set_and_old_set_stays_reachable(tmp_path):
    catalog = _fixture_catalog(tmp_path)
    loaded = select(catalog, ["gmail"])
    swapped = hot_swap(loaded, catalog, ["shopping", "github"])
    assert [e.name for e in swapped] == ["shopping", "github"]
    assert "gmail" in {e.name for e in catalog}
    assert "gmail" in "\n".join(menu(catalog))


def test_real_catalog_knows_the_estate():
    if not Path("/opt/muse/skills").is_dir():
        pytest.skip("estate skills dir absent on this machine")
    skills = [Path("/opt/muse/skills"), Path.home() / "workspace" / "custom-skills"]
    connectors = [Path("/opt/hatch/connectors"), Path.home() / "workspace" / "custom-connectors"]
    catalog = build_catalog(skills, connectors)
    assert len(catalog) > 100
    names = {e.name for e in catalog}
    assert "shopping" in names
    assert "gmail" in names
