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
        outcome_state=lambda: {"recorded": False},
    )


def _arm_model_attractor_preflight(monkeypatch, *, ok: bool = True) -> None:
    state = {"value": None}
    validation = SimpleNamespace(
        ok=ok,
        status="complete" if ok else "continuation_required",
        errors=() if ok else ("frontier evidence unavailable",),
    )

    def automatic():
        state["value"] = validation
        return validation

    def getter():
        return state["value"]

    monkeypatch.setattr(boot, "automatic_model_attractor_defense", automatic)
    monkeypatch.setattr(boot, "get_in_process_model_attractor_validation", getter)
    monkeypatch.setattr(
        boot,
        "validate_runtime_strict_frontier",
        lambda: SimpleNamespace(ok=True, errors=()),
    )


def _arm_boot(monkeypatch) -> list[str]:
    calls: list[str] = []
    _arm_model_attractor_preflight(monkeypatch)
    for index, (automatic_name, getter_name) in enumerate(_GATE_BINDINGS):
        state = {"value": None}
        validation = SimpleNamespace(ok=True, status="complete", errors=())

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

    monkeypatch.setattr(boot, "enforce_outcome_fidelity", lambda kernel: kernel)
    monkeypatch.setattr(
        boot,
        "create_operator_sovereign_runtime_kernel",
        lambda *, observed_gates: _fake_kernel(gates=observed_gates),
    )
    boot._IN_PROCESS = None
    return calls


def test_complete_boot_records_all_observations_and_creates_kernel(monkeypatch) -> None:
    calls = _arm_boot(monkeypatch)

    session = apply_strongest_boot()

    assert calls == list(EXPECTED_GATES)
    assert session.status == "complete"
    assert session.gates == EXPECTED_GATES
    assert session.observations == ()
    assert session.runtime_id == "runtime-proof"
    assert get_in_process_strong_boot() is session
    assert boot.os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] == "complete"


def test_missing_frontier_proof_is_observation_not_permission_gate(monkeypatch) -> None:
    _arm_boot(monkeypatch)
    monkeypatch.setattr(
        boot,
        "validate_runtime_strict_frontier",
        lambda: SimpleNamespace(ok=False, errors=("boot receipt missing",)),
    )

    session = apply_strongest_boot()

    assert session.status == "degraded"
    assert session.gates == EXPECTED_GATES
    assert any("boot receipt missing" in item for item in session.observations)
    assert session.runtime_id == "runtime-proof"


def test_incomplete_gate_degrades_and_later_checks_still_run(monkeypatch) -> None:
    calls = _arm_boot(monkeypatch)
    state = {"value": None}
    validation = SimpleNamespace(
        ok=False,
        status="continuation_required",
        errors=("continuity receipt unavailable",),
    )

    def incomplete_notion():
        calls.append("notion_continuity")
        state["value"] = validation
        return validation

    monkeypatch.setattr(boot, "automatic_notion_continuity_preflight", incomplete_notion)
    monkeypatch.setattr(boot, "get_in_process_notion_validation", lambda: state["value"])

    session = apply_strongest_boot()

    assert calls == list(EXPECTED_GATES)
    assert session.status == "degraded"
    assert "notion_continuity" not in session.gates
    assert session.gates == EXPECTED_GATES[1:]
    assert any("continuity receipt unavailable" in item for item in session.observations)
    assert boot.os.environ["GLACIEREQ_STRONG_BOOT_STATUS"] == "degraded"


def test_model_attractor_incomplete_does_not_prevent_runtime_creation(monkeypatch) -> None:
    _arm_boot(monkeypatch)
    _arm_model_attractor_preflight(monkeypatch, ok=False)
    created = {"value": False}

    def factory(*, observed_gates):
        created["value"] = True
        return _fake_kernel(gates=observed_gates)

    monkeypatch.setattr(boot, "create_operator_sovereign_runtime_kernel", factory)

    session = apply_strongest_boot()

    assert created["value"] is True
    assert session.status == "degraded"
    assert any("frontier evidence unavailable" in item for item in session.observations)


def test_require_strong_boot_automatically_establishes_context(monkeypatch) -> None:
    calls = _arm_boot(monkeypatch)
    boot._IN_PROCESS = None

    session = require_strong_boot()

    assert session is get_in_process_strong_boot()
    assert calls == list(EXPECTED_GATES)


def test_strong_boot_is_idempotent_inside_process(monkeypatch) -> None:
    calls = _arm_boot(monkeypatch)

    first = apply_strongest_boot()
    second = apply_strongest_boot()

    assert second is first
    assert calls == list(EXPECTED_GATES)


def test_concurrent_first_boot_publishes_one_session_and_kernel(monkeypatch) -> None:
    calls = _arm_boot(monkeypatch)
    kernel_calls: list[str] = []

    def kernel_factory(*, observed_gates):
        kernel_calls.append("create")
        return _fake_kernel(gates=observed_gates)

    monkeypatch.setattr(boot, "create_operator_sovereign_runtime_kernel", kernel_factory)

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
            observations=(),
            runtime_kernel=_fake_kernel(),
            _seal=object(),
        )


def test_kernel_must_bind_same_observed_gate_set(monkeypatch) -> None:
    _arm_boot(monkeypatch)
    monkeypatch.setattr(
        boot,
        "create_operator_sovereign_runtime_kernel",
        lambda *, observed_gates: _fake_kernel(gates=observed_gates[:-1]),
    )

    with pytest.raises(StrongBootViolation, match="startup observations"):
        apply_strongest_boot()


def test_kernel_must_begin_before_any_task_is_bound(monkeypatch) -> None:
    _arm_boot(monkeypatch)
    monkeypatch.setattr(
        boot,
        "create_operator_sovereign_runtime_kernel",
        lambda *, observed_gates: _fake_kernel(phase="ready", gates=observed_gates),
    )

    with pytest.raises(StrongBootViolation, match="must begin bootstrapped"):
        apply_strongest_boot()


def test_explicit_operator_fidelity_hard_lock_bypass_remains_terminal(monkeypatch) -> None:
    _arm_boot(monkeypatch)

    def reject_bypass():
        raise SystemExit(78)

    monkeypatch.setattr(boot, "automatic_operator_fidelity_lock", reject_bypass)
    monkeypatch.setattr(boot, "get_in_process_operator_fidelity_lock", lambda: None)

    with pytest.raises(SystemExit) as exc_info:
        apply_strongest_boot()

    assert exc_info.value.code == 78
    assert get_in_process_strong_boot() is None


def test_boot_observation_mode_restores_caller_environment(monkeypatch) -> None:
    _arm_boot(monkeypatch)
    monkeypatch.setenv("CASEY_AUTO_BOOT_MODE", "strict")

    session = apply_strongest_boot()

    assert session.status == "complete"
    assert boot.os.environ["CASEY_AUTO_BOOT_MODE"] == "strict"


def test_control_plane_executes_runtime_with_exact_boot_objects(monkeypatch) -> None:
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
    injected = captured["init_globals"]
    assert injected["APEX_STRONG_BOOT_SESSION"] is session
    assert injected["APEX_RUNTIME_KERNEL"] is kernel


def test_control_plane_still_stops_on_true_boot_integrity_failure(monkeypatch, capsys) -> None:
    fake_boot = ModuleType("apex_strong_boot")

    def fail_boot():
        raise RuntimeError("runtime seal invalid")

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
