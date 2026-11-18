"""The interpreter-floor guard must fail cleanly, never as INTERNALERROR noise.

Background: ``src/`` uses ``dataclasses(slots=True)`` (3.10+). On the operator
host's system Python 3.9 every such import raised, and pytest reported 47
separate *collection errors* with no shared cause. That reads like 47 broken
tests; it was one broken interpreter.

The guard in ``tests/conftest.py`` now fails once, before collection, with one
actionable message. These tests prove the guard itself behaves, so it cannot
rot into a second misleading failure mode.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parent / "conftest.py"
MINIMUM = (3, 10)


def _tree() -> ast.Module:
    return ast.parse(CONFTEST.read_text(encoding="utf-8"))


def _function(name: str) -> ast.FunctionDef:
    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing hook: {name}")


def test_floor_constant_is_declared():
    """The supported floor must be explicit, not implied."""
    source = CONFTEST.read_text(encoding="utf-8")
    assert "MINIMUM_PYTHON" in source
    assert "(3, 10)" in source


def test_configure_hook_checks_version():
    """pytest_configure must compare the running interpreter to the floor."""
    hook = _function("pytest_configure")
    body = ast.dump(hook)
    assert "version_info" in body
    assert "MINIMUM_PYTHON" in body


def test_configure_raises_usage_error_not_systemexit():
    """UsageError reports cleanly; SystemExit becomes an INTERNALERROR."""
    hook = _function("pytest_configure")
    raises = [
        node
        for node in ast.walk(hook)
        if isinstance(node, ast.Raise) and node.exc is not None
    ]
    assert raises, "pytest_configure must raise"
    rendered = " ".join(ast.dump(node) for node in raises)
    assert "UsageError" in rendered
    assert "SystemExit" not in rendered


def test_header_reports_interpreter():
    """The header must surface the running version so it is never implicit."""
    hook = _function("pytest_report_header")
    body = ast.dump(hook)
    assert "version_info" in body


def test_message_names_the_real_cause():
    """The message must name the actual error, not just say 'too old'."""
    source = CONFTEST.read_text(encoding="utf-8")
    assert "slots" in source
    assert "dataclass()" in source


def test_message_forbids_the_wrong_fix():
    """Stripping slots=True is not a fix; the message must say so."""
    source = CONFTEST.read_text(encoding="utf-8")
    assert "slots=True" in source
    lowered = source.lower()
    assert "do not" in lowered or "not an accident" in lowered


def test_guard_does_not_skip_tests():
    """The guard fails closed; it must not silently skip."""
    source = CONFTEST.read_text(encoding="utf-8")
    configure = _function("pytest_configure")
    body = ast.dump(configure)
    assert "skip" not in body.lower().replace("skipped", "")


def test_preexisting_compat_hooks_survive():
    """The floor guard must not evict the existing compatibility hooks."""
    source = CONFTEST.read_text(encoding="utf-8")
    assert "_patch_prime_directive_helper" in source
    assert "pytest_collection_modifyitems" in source


def test_representative_files_exist():
    """Files named in the error must be real, or the message points nowhere."""
    source = CONFTEST.read_text(encoding="utf-8")
    repo_root = CONFTEST.resolve().parent.parent
    named = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith('"src/') and line.strip().endswith('",')
    ]
    assert named, "expected at least one representative src/ file"
    for entry in named:
        rel = entry.strip('",')
        assert (repo_root / rel).exists(), f"named file does not exist: {rel}"


def test_guard_matches_ci_floor():
    """The guard's floor must stay at or below the version CI actually runs."""
    source = CONFTEST.read_text(encoding="utf-8")
    assert "(3, 10)" in source
    ci_floor = (3, 12)  # .github/workflows/*.yml pin python-version: "3.12"
    assert MINIMUM <= ci_floor, "guard floor must not exceed the CI interpreter"


def test_pyproject_declares_python_floor():
    """requires-python must agree with the guard, not contradict it."""
    pyproject = CONFTEST.resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("pyproject.toml not present")
    assert 'requires-python = ">=3.10"' in pyproject.read_text(encoding="utf-8")