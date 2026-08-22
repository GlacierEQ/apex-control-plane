from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime_execution_guard import (
    enforce_verified_runtime_boundary,
    legacy_runtime_is_direct,
)


def test_guard_identifies_only_legacy_runtime_direct_execution() -> None:
    assert legacy_runtime_is_direct("src/control_plane_runtime.py") is True
    assert legacy_runtime_is_direct("src/control_plane.py") is False
    assert legacy_runtime_is_direct("src/verified_runtime_entrypoint.py") is False


def test_direct_legacy_runtime_is_fail_closed(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        enforce_verified_runtime_boundary(
            argv0="src/control_plane_runtime.py",
            testing=False,
        )

    assert exc_info.value.code == 78
    error = capsys.readouterr().err
    assert "direct control_plane_runtime execution is disabled" in error
    assert '"runtime_authorized": false' in error
    assert '"external_action_authorized": false' in error


def test_verified_entrypoints_are_not_blocked() -> None:
    enforce_verified_runtime_boundary(argv0="src/control_plane.py", testing=False)
    enforce_verified_runtime_boundary(
        argv0="src/verified_runtime_entrypoint.py",
        testing=False,
    )
