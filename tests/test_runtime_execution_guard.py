from __future__ import annotations

from pathlib import Path
import sys

import runtime_execution_guard as guard
from runtime_execution_guard import (
    enforce_verified_runtime_boundary,
    legacy_runtime_is_direct,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_guard_identifies_only_legacy_runtime_direct_execution() -> None:
    assert legacy_runtime_is_direct("src/control_plane_runtime.py") is True
    assert legacy_runtime_is_direct("src/control_plane.py") is False
    assert legacy_runtime_is_direct("src/verified_runtime_entrypoint.py") is False


def test_direct_legacy_runtime_reroutes_to_canonical_entrypoint(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_execv(executable: str, argv: list[str]) -> None:
        captured["executable"] = executable
        captured["argv"] = argv

    monkeypatch.setattr(guard.os, "execv", fake_execv)
    monkeypatch.setattr(guard.sys, "argv", ["src/control_plane_runtime.py", "--demo"])

    enforce_verified_runtime_boundary(
        argv0="src/control_plane_runtime.py",
        testing=False,
    )

    assert captured["executable"] == sys.executable
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert Path(argv[1]).name == "control_plane.py"
    assert argv[2:] == ["--demo"]
    error = capsys.readouterr().err
    assert '"boot_status": "rerouting"' in error
    assert '"runtime_authorized": true' in error
    assert '"external_action_authorized": "route_local"' in error


def test_verified_entrypoints_are_not_rerouted(monkeypatch) -> None:
    def forbidden_execv(*args, **kwargs):
        raise AssertionError("verified entrypoint must not be rerouted")

    monkeypatch.setattr(guard.os, "execv", forbidden_execv)
    enforce_verified_runtime_boundary(argv0="src/control_plane.py", testing=False)
    enforce_verified_runtime_boundary(
        argv0="src/verified_runtime_entrypoint.py",
        testing=False,
    )


def test_reroute_transport_failure_is_real_runtime_error(monkeypatch) -> None:
    def broken_execv(*args, **kwargs):
        raise OSError("exec transport unavailable")

    monkeypatch.setattr(guard.os, "execv", broken_execv)
    monkeypatch.setattr(guard.sys, "argv", ["src/control_plane_runtime.py"])

    try:
        enforce_verified_runtime_boundary(
            argv0="src/control_plane_runtime.py",
            testing=False,
        )
    except RuntimeError as exc:
        assert "canonical APEX runtime reroute failed" in str(exc)
    else:
        raise AssertionError("real os.execv failure must surface as a runtime error")
