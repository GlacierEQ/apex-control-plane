from __future__ import annotations

from pathlib import Path

import pytest

from strict_frontier_preflight import _resolve_frontier_source


def test_source_and_provider_namespaces_use_distinct_roots(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    provider_root = tmp_path / "provider"
    source_root.mkdir()
    provider_root.mkdir()
    (source_root / "operator.txt").write_bytes(b"operator-source")
    provider_file = provider_root / "github-actions" / "run" / "42" / "readback"
    provider_file.parent.mkdir(parents=True)
    provider_file.write_bytes(b"provider-readback")

    monkeypatch.setenv("GLACIEREQ_FRONTIER_SOURCE_ROOT", str(source_root))
    monkeypatch.setenv("GLACIEREQ_PROVIDER_READBACK_ROOT", str(provider_root))

    assert _resolve_frontier_source("file:operator.txt") == b"operator-source"
    assert (
        _resolve_frontier_source("provider://github-actions/run/42/readback")
        == b"provider-readback"
    )


def test_provider_reference_cannot_fall_through_to_source_root(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    fake = source_root / "github-actions" / "run" / "42" / "readback"
    fake.parent.mkdir(parents=True)
    fake.write_bytes(b"forged-from-source-root")

    monkeypatch.setenv("GLACIEREQ_FRONTIER_SOURCE_ROOT", str(source_root))
    monkeypatch.delenv("GLACIEREQ_PROVIDER_READBACK_ROOT", raising=False)

    with pytest.raises(FileNotFoundError, match="GLACIEREQ_PROVIDER_READBACK_ROOT"):
        _resolve_frontier_source("provider://github-actions/run/42/readback")


def test_provider_output_isolated_under_provider_output_namespace(tmp_path: Path, monkeypatch) -> None:
    provider_root = tmp_path / "provider"
    output = provider_root / "outputs" / "strict-test"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"verified-output")
    monkeypatch.setenv("GLACIEREQ_PROVIDER_READBACK_ROOT", str(provider_root))

    assert _resolve_frontier_source("provider-output:strict-test") == b"verified-output"


def test_authority_roots_reject_path_escape(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    provider_root = tmp_path / "provider"
    source_root.mkdir()
    provider_root.mkdir()
    monkeypatch.setenv("GLACIEREQ_FRONTIER_SOURCE_ROOT", str(source_root))
    monkeypatch.setenv("GLACIEREQ_PROVIDER_READBACK_ROOT", str(provider_root))

    with pytest.raises(ValueError, match="escapes configured root"):
        _resolve_frontier_source("file:../outside")
    with pytest.raises(ValueError, match="escapes configured root"):
        _resolve_frontier_source("provider://../outside")
