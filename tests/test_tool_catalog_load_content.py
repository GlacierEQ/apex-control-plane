"""Subprocess acceptance for atomic capability document loading."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "tool_catalog.py"


def invoke(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_selected_document_content_is_actually_loaded(tmp_path):
    root = tmp_path / "skills"
    doc = root / "alpha" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Alpha\\n- performs alpha\\n", encoding="utf-8")
    result = invoke("--skills", root, "--select", "skill:alpha", "--load-content")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["content"] == doc.read_text(encoding="utf-8")
    assert payload[0]["kind"] == "skill"
    assert payload[0]["sha256"] == hashlib.sha256(doc.read_bytes()).hexdigest()


def test_missing_selection_never_leaks_partial_content(tmp_path):
    root = tmp_path / "skills"
    doc = root / "alpha" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("alpha", encoding="utf-8")
    result = invoke("--skills", root, "--select", "skill:alpha", "--select", "missing", "--load-content")
    assert result.returncode == 2
    assert result.stdout == ""


def test_disappearing_document_never_emits_partial_json(tmp_path, monkeypatch, capsys):
    from src import tool_catalog
    entry = tool_catalog.CatalogEntry("gone", "skill", "", str(tmp_path / "gone.md"))
    monkeypatch.setattr(tool_catalog, "build_catalog", lambda *_: [entry])
    assert tool_catalog.main(["--select", "skill:gone", "--load-content"]) == 2
    assert capsys.readouterr().out == ""


def test_pinned_digest_rejects_changed_document_without_partial_output(tmp_path):
    root = tmp_path / "skills"
    doc = root / "alpha" / "SKILL.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("original", encoding="utf-8")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    good = invoke("--skills", root, "--select", "skill:alpha", "--load-content", "--expect-sha256", digest)
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)[0]["sha256"] == digest
    doc.write_text("changed", encoding="utf-8")
    bad = invoke("--skills", root, "--select", "skill:alpha", "--load-content", "--expect-sha256", digest)
    assert bad.returncode == 2
    assert bad.stdout == ""
    assert "digest mismatch" in bad.stderr


def test_digest_pin_requires_explicit_matching_selection(tmp_path):
    result = invoke("--skills", tmp_path, "--expect-sha256", "0" * 64)
    assert result.returncode == 2
    assert result.stdout == ""
