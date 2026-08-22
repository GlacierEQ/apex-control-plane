from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import apex_strong_boot as boot
from apex_strong_boot import (
    EXPECTED_GATES,
    StrongBootSession,
    StrongBootViolation,
    apply_strongest_boot,
    get_in_process_strong_boot,
    require_strong_boot,
)


_GATE_BINDINGS = (
    ("automatic_notion_continuity_preflight", "get_in_process_notion_validation"),
    ("automatic_prime_directive_boot", "get_in_process_boot_validation"),
    ("automatic_operator_fidelity_lock", "get_in_process_operator_fidelity_lock"),
    ("automatic_operator_fidelity_preflight", "get_in_process_operator_fidelity_validation"),
    ("automatic_apex_enforced_startup", "get_in_process_apex_validation"),
)


def _fake_kernel(*, phase: str = "bootstrapped", gates=EXPECTED_GATES):
    snapshot = SimpleNamespace(
        phase=phase,
        task_id=None,
        startup_gates=tuple(gates),
    )
    return SimpleNamespace(
        runtime_id="runtime-proof",
        snapshot=lambda: snapshot,
    )


def _arm_complete_boot(monkeypatch) -> list[str]:
    calls: list[str] = []
    for index, (automatic_name, getter_name) in enumerate(_GATE_BINDINGS):
        state = {"value": None}
        validation = SimpleNamespace(ok=True, status="complete")

        def automatic(
            *,
            state=state,
            validation=validation,
            index=index,
        ):
            calls.append(EXPECTED_GATES[index])
            state["value"] = validation
            return validation

        def getter(*, state=state):
            return state["value"]

        monkeypatch.setattr(boot, automatic_name, automatic)
        monkeypatch.setattr(boot, getter_name, getter)

    monkeypatch.setattr(boot, "create_verified_runtime_kernel", lambda: _fake_kernel())
    boot._IN_PROCESS = None
    return calls


def test_strong_boot_runs_exact_gate_sequence_and_creates_kernel(monkeypatch) -> None:
    calls = _arm_complete_boot(monkeypatch)

    session = apply_strongest_boot()

    assert calls == list(EXPECTED_GATES)
    assert session.status == "complete"
    assert session.gates == EXPECTED_GATES
    assert session.runtime_id == "runtime-proof"
    assert get_in_process_strong_boot() is session
    assert boot.os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] == "complete"


def test_strong_boot_is_idempotent_inside_process(monkeypatch) -> None:
    calls = _arm_complete_boot(monkeypatch)

    first = apply_strongest_boot()
    second = apply_strongest_boot()

    assert second is first
    assert calls == list(EXPECTED_GATES)


def test_concurrent_first_boot_publishes_one_session_and_kernel(monkeypatch) -> None:
    calls = _arm_complete_boot(monkeypatch)
    kernel_calls: list[str] = []

    def kernel_factory():
        kernel_calls.append("create")
        return _fake_kernel()

    monkeypatch.setattr(boot, "create_verified_runtime_kernel", kernel_factory)

    with ThreadPoolExecutor(max_workers=16) as pool:
        sessions = list(pool.map(lambda _: apply_strongest_boot(), range(64)))

    assert len({id(session) for session in sessions}) == 1
    assert len({id(session.runtime_kernel) for session in sessions}) == 1
    assert calls == list(EXPECTED_GATES)
    assert kernel_calls == ["create"]


def test_session_cannot_be_forged() -> None:
    with pytest.raises(TypeError, match="issued by apply_strongest_boot"):
        StrongBootSession(
            session_id="forged",
            status="complete",
            created_at=boot.datetime.now(boot.UTC),
            gates=EXPECTED_GATES,
            runtime_kernel=_fake_kernel(),
            _seal=object(),
        )


def test_missing_in_process_validation_fails_closed(monkeypatch) -> None:
    _arm_complete_boot(monkeypatch)
    validation = SimpleNamespace(ok=True, status="complete")
    monkeypatch.setattr(boot, "automatic_prime_directive_boot", lambda: validation)
    monkeypatch.setattr(boot, "get_in_process_boot_validation", lambda: None)

    with pytest.raises(StrongBootViolation, match="in-process validation missing"):
        apply_strongest_boot()

    assert get_in_process_strong_boot() is None


def test_incomplete_gate_preserves_later_diagnostics_before_block(monkeypatch) -> None:
    calls = _arm_complete_boot(monkeypatch)
    state = {"value": None}
    validation = SimpleNamespace(ok=False, status="continuation_required")

    def incomplete_notion():
        calls.append("notion_continuity")
        state["value"] = validation
        return validation

    monkeypatch.setattr(boot, "automatic_notion_continuity_preflight", incomplete_notion)
    monkeypatch.setattr(boot, "get_in_process_notion_validation", lambda: state["value"])

    with pytest.raises(StrongBootViolation, match="notion_continuity"):
        apply_strongest_boot()

    assert calls == list(EXPECTED_GATES)
    assert boot.os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] == "blocked"


def test_incomplete_gate_fails_before_kernel_creation(monkeypatch) -> None:
    _arm_complete_boot(monkeypatch)
    state = {"value": None}
    validation = SimpleNamespace(ok=False, status="continuation_required")

    def automatic():
        state["value"] = validation
        return validation

    monkeypatch.setattr(boot, "automatic_operator_fidelity_preflight", automatic)
    monkeypatch.setattr(
        boot,
        "get_in_process_operator_fidelity_validation",
        lambda: state["value"],
    )
    kernel_called = {"value": False}

    def kernel_factory():
        kernel_called["value"] = True
        return _fake_kernel()

    monkeypatch.setattr(boot, "create_verified_runtime_kernel", kernel_factory)

    with pytest.raises(StrongBootViolation, match="operator_fidelity: validation ok is not true"):
        apply_strongest_boot()

    assert kernel_called["value"] is False


def test_kernel_must_bind_same_complete_gate_set(monkeypatch) -> None:
    _arm_complete_boot(monkeypatch)
    monkeypatch.setattr(
        boot,
        "create_verified_runtime_kernel",
        lambda: _fake_kernel(gates=EXPECTED_GATES[:-1]),
    )

    with pytest.raises(StrongBootViolation, match="startup-gate proof"):
        apply_strongest_boot()


def test_kernel_must_begin_before_any_task_is_bound(monkeypatch) -> None:
    _arm_complete_boot(monkeypatch)
    monkeypatch.setattr(
        boot,
        "create_verified_runtime_kernel",
        lambda: _fake_kernel(phase="ready"),
    )

    with pytest.raises(StrongBootViolation, match="must begin bootstrapped"):
        apply_strongest_boot()


def test_require_strong_boot_does_not_secretly_run_boot(monkeypatch) -> None:
    _arm_complete_boot(monkeypatch)
    boot._IN_PROCESS = None

    with pytest.raises(StrongBootViolation, match="has not been established"):
        require_strong_boot()


def test_control_plane_executes_verified_boundary_with_exact_boot_objects(
    monkeypatch,
) -> None:
    kernel = SimpleNamespace(runtime_id="kernel-1")
    session = SimpleNamespace(session_id="session-1", runtime_kernel=kernel)
    fake_boot = ModuleType("apex_strong_boot")
    fake_boot.apply_strongest_boot = lambda: session
    fake_auto = ModuleType("auto_boot")
    fake_auto.EXIT_BOOT_BLOCKED = 78
    monkeypatch.setitem(sys.modules, "apex_strong_boot", fake_boot)
    monkeypatch.setitem(sys.modules, "auto_boot", fake_auto)

    captured: dict[str, object] = {}

    def fake_run_path(path, *, run_name, init_globals):
        captured["path"] = str(path)
        captured["run_name"] = run_name
        captured["init_globals"] = init_globals
        return {}

    monkeypatch.setattr(runpy, "run_path", fake_run_path)
    target = SRC / "control_plane.py"
    namespace = {"__name__": "__main__", "__file__": str(target)}
    exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)

    assert captured["path"].endswith("verified_runtime_entrypoint.py")
    assert captured["run_name"] == "__main__"
    injected = captured["init_globals"]
    assert injected["APEX_STRONG_BOOT_SESSION"] is session
    assert injected["APEX_RUNTIME_KERNEL"] is kernel


def test_control_plane_blocks_before_runtime_when_strong_boot_fails(
    monkeypatch, capsys
) -> None:
    fake_boot = ModuleType("apex_strong_boot")

    def fail_boot():
        raise RuntimeError("boot proof missing")

    fake_boot.apply_strongest_boot = fail_boot
    fake_auto = ModuleType("auto_boot")
    fake_auto.EXIT_BOOT_BLOCKED = 78
    monkeypatch.setitem(sys.modules, "apex_strong_boot", fake_boot)
    monkeypatch.setitem(sys.modules, "auto_boot", fake_auto)

    called = {"runtime": False}

    def forbidden_run_path(*args, **kwargs):
        called["runtime"] = True
        raise AssertionError("runtime must not load")

    monkeypatch.setattr(runpy, "run_path", forbidden_run_path)
    target = SRC / "control_plane.py"
    namespace = {"__name__": "__main__", "__file__": str(target)}

    with pytest.raises(SystemExit) as exc_info:
        exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)

    assert exc_info.value.code == 78
    assert called["runtime"] is False
    assert '"strong_boot_status": "blocked"' in capsys.readouterr().err


def test_sitecustomize_executes_same_strong_boot_session(monkeypatch) -> None:
    kernel = SimpleNamespace(runtime_id="kernel-site")
    session = SimpleNamespace(session_id="session-site", runtime_kernel=kernel)
    fake_boot = ModuleType("apex_strong_boot")
    calls: list[str] = []

    def fake_apply():
        calls.append("boot")
        return session

    fake_boot.apply_strongest_boot = fake_apply
    monkeypatch.setitem(sys.modules, "apex_strong_boot", fake_boot)
    monkeypatch.setattr(sys, "argv", [str(SRC / "verified_runtime_entrypoint.py")])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("CASEY_AUTO_BOOT_TESTING", raising=False)
    monkeypatch.delenv("CASEY_AUTO_BOOT", raising=False)
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")

    target = SRC / "sitecustomize.py"
    namespace = {"__name__": "sitecustomize_test", "__file__": str(target)}
    exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)

    assert calls == ["boot"]
    assert namespace["APEX_STRONG_BOOT_SESSION"] is session
    assert namespace["APEX_RUNTIME_KERNEL"] is kernel
