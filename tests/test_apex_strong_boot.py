from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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


def test_control_plane_and_sitecustomize_share_one_boot_orchestrator() -> None:
    control_plane = (SRC / "control_plane.py").read_text(encoding="utf-8")
    sitecustomize = (SRC / "sitecustomize.py").read_text(encoding="utf-8")

    assert "apply_strongest_boot" in control_plane
    assert "apply_strongest_boot" in sitecustomize
    for legacy_stage in (
        "automatic_notion_continuity_preflight",
        "automatic_prime_directive_boot",
        "automatic_operator_fidelity_lock",
        "automatic_operator_fidelity_preflight",
        "automatic_apex_enforced_startup",
    ):
        assert legacy_stage not in control_plane
        assert legacy_stage not in sitecustomize
