from __future__ import annotations

from types import SimpleNamespace

import apex_strong_boot as boot
import strict_frontier_preflight as preflight
from executable_frontier_authority import FrontierAuthorizationResult


def test_runtime_preflight_reports_unresolved_frontier_without_global_authority(monkeypatch) -> None:
    monkeypatch.setattr(preflight, "receipt_from_environment", lambda: None)
    result = preflight.validate_runtime_strict_frontier()
    assert result.ok is False
    assert result.status == "frontier_authorization_unresolved"
    assert any("requires a boot receipt" in error for error in result.errors)


def test_runtime_preflight_delegates_to_strict_authority(monkeypatch) -> None:
    receipt = {"frontier_authority": {"frontier_id": "frontier:test"}}
    observed: dict[str, object] = {}

    def fake_validate(value, *, resolver):
        observed["receipt"] = value
        observed["resolver"] = resolver
        return FrontierAuthorizationResult(True, "frontier_authorized", ())

    monkeypatch.setattr(preflight, "receipt_from_environment", lambda: receipt)
    monkeypatch.setattr(
        preflight, "validate_strict_executable_frontier_authority", fake_validate
    )
    result = preflight.validate_runtime_strict_frontier()
    assert result.ok is True
    assert observed["receipt"] is receipt
    assert callable(observed["resolver"])


def test_strong_boot_accumulates_model_attractor_diagnostics_when_frontier_is_unresolved(
    monkeypatch,
) -> None:
    findings: list[str] = []
    strict = FrontierAuthorizationResult(
        False,
        "frontier_authorization_unresolved",
        ("dependency enumeration missing",),
    )
    validation = SimpleNamespace(
        ok=False,
        status="uplift_required",
        errors=("model attractor context incomplete",),
    )
    state = {"value": None}
    calls: list[str] = []

    monkeypatch.setattr(boot, "validate_runtime_strict_frontier", lambda: strict)
    monkeypatch.setattr(
        boot, "get_in_process_model_attractor_validation", lambda: state["value"]
    )

    def automatic():
        calls.append("model-attractor")
        state["value"] = validation
        return validation

    monkeypatch.setattr(boot, "automatic_model_attractor_defense", automatic)
    boot._run_model_attractor_preflight(findings)

    assert calls == ["model-attractor"]
    assert any(
        item == "strict_executable_frontier_authority: dependency enumeration missing"
        for item in findings
    )
    assert any("model_attractor_defense" in item for item in findings)
    assert any("model attractor context incomplete" in item for item in findings)


def test_strong_boot_runs_model_attractor_when_frontier_is_resolved(monkeypatch) -> None:
    findings: list[str] = []
    strict = FrontierAuthorizationResult(True, "frontier_authorized", ())
    validation = SimpleNamespace(ok=True, status="complete", errors=())
    state = {"value": None}
    calls: list[str] = []

    monkeypatch.setattr(boot, "validate_runtime_strict_frontier", lambda: strict)
    monkeypatch.setattr(
        boot, "get_in_process_model_attractor_validation", lambda: state["value"]
    )

    def automatic():
        calls.append("model-attractor")
        state["value"] = validation
        return validation

    monkeypatch.setattr(boot, "automatic_model_attractor_defense", automatic)
    boot._run_model_attractor_preflight(findings)
    assert findings == []
    assert calls == ["model-attractor"]
