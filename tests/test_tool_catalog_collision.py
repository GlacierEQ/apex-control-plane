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
