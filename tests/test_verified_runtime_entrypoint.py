from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import verified_runtime_entrypoint as entry
from apex_strong_boot import EXPECTED_GATES
from verified_runtime_entrypoint import RuntimeBindingViolation


class FakeKernel:
    def __init__(self) -> None:
        self.runtime_id = "runtime-test"
        self.phase = SimpleNamespace(value="bootstrapped")
        self.task_id = None
        self.receipts: list[str] = []
        self.calls: list[tuple[str, object]] = []

    def snapshot(self):
        return SimpleNamespace(
            phase=self.phase.value,
            task_id=self.task_id,
            startup_gates=EXPECTED_GATES,
            receipt_kinds=tuple(self.receipts),
        )

    def bind_task(self, **kwargs):
        self.calls.append(("bind_task", kwargs))
        self.task_id = "task-1"
        self.phase.value = "ready"
        return self.snapshot()

    def assert_instruction_fidelity(self, instruction):
        self.calls.append(("assert_instruction_fidelity", instruction))

    def begin(self):
        self.calls.append(("begin", None))
        self.phase.value = "observing"
        return self.snapshot()

    def record_observation(self, reference, *, details=None):
        self.calls.append(("record_observation", reference))
        self.receipts.append("observation")
        self.phase.value = "verifying"
        return self.snapshot()

    def record_verification(self, reference, *, passed, details=None):
        self.calls.append(("record_verification", (reference, passed)))
        self.receipts.append("verification")
        self.phase.value = "readback" if passed else "blocked"
        return self.snapshot()

    def record_readback(
        self,
        reference,
        *,
        matches_expected_state,
        target_reached,
        details=None,
    ):
        self.calls.append(
            (
                "record_readback",
                (reference, matches_expected_state, target_reached),
            )
        )
        self.receipts.append("readback")
        self.phase.value = (
            "complete" if matches_expected_state and target_reached else "blocked"
        )
        return self.snapshot()

    def block(self, reason, *, reference):
        self.calls.append(("block", (reason, reference)))
        self.phase.value = "blocked"
        return self.snapshot()


def _session(kernel: FakeKernel):
    return SimpleNamespace(
        session_id="session-test",
        status="complete",
        gates=EXPECTED_GATES,
        runtime_kernel=kernel,
    )


def test_runtime_context_requires_exact_injected_session_and_kernel(monkeypatch) -> None:
    kernel = FakeKernel()
    session = _session(kernel)
    monkeypatch.setattr(entry, "require_strong_boot", lambda: session)

    resolved_session, resolved_kernel = entry.require_runtime_context(
        {
            "APEX_STRONG_BOOT_SESSION": session,
            "APEX_RUNTIME_KERNEL": kernel,
        }
    )

    assert resolved_session is session
    assert resolved_kernel is kernel


def test_runtime_context_rejects_session_or_kernel_identity_mismatch(monkeypatch) -> None:
    kernel = FakeKernel()
    session = _session(kernel)
    monkeypatch.setattr(entry, "require_strong_boot", lambda: session)

    with pytest.raises(RuntimeBindingViolation, match="session does not match"):
        entry.require_runtime_context(
            {
                "APEX_STRONG_BOOT_SESSION": _session(kernel),
                "APEX_RUNTIME_KERNEL": kernel,
            }
        )

    with pytest.raises(RuntimeBindingViolation, match="does not belong"):
        entry.require_runtime_context(
            {
                "APEX_STRONG_BOOT_SESSION": session,
                "APEX_RUNTIME_KERNEL": FakeKernel(),
            }
        )


def test_verified_smoke_traverses_kernel_to_complete_readback(monkeypatch) -> None:
    kernel = FakeKernel()
    session = _session(kernel)
    monkeypatch.setattr(entry, "require_strong_boot", lambda: session)
    monkeypatch.setattr(
        entry,
        "_process_synthetic_event",
        lambda: {
            "status": "completed",
            "external_action_authorized": False,
            "value": "verified",
        },
    )

    payload = entry.execute_verified_local_smoke(
        {
            "APEX_STRONG_BOOT_SESSION": session,
            "APEX_RUNTIME_KERNEL": kernel,
        }
    )

    assert [name for name, _ in kernel.calls] == [
        "bind_task",
        "assert_instruction_fidelity",
        "begin",
        "record_observation",
        "record_verification",
        "record_readback",
    ]
    assert kernel.phase.value == "complete"
    assert payload["apex_runtime"]["phase"] == "complete"
    assert payload["apex_runtime"]["receipt_kinds"] == [
        "observation",
        "verification",
        "readback",
    ]
    assert payload["apex_runtime"]["runtime_id"] == "runtime-test"
    assert payload["apex_runtime"]["strong_boot_session_id"] == "session-test"
    assert payload["apex_runtime"]["external_action_authorized"] is False


def test_verified_smoke_failure_is_bound_as_runtime_blocker(monkeypatch) -> None:
    kernel = FakeKernel()
    session = _session(kernel)
    monkeypatch.setattr(entry, "require_strong_boot", lambda: session)

    def fail_smoke():
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(entry, "_process_synthetic_event", fail_smoke)

    with pytest.raises(RuntimeError, match="synthetic failure"):
        entry.execute_verified_local_smoke(
            {
                "APEX_STRONG_BOOT_SESSION": session,
                "APEX_RUNTIME_KERNEL": kernel,
            }
        )

    assert kernel.phase.value == "blocked"
    assert kernel.calls[-1][0] == "block"
