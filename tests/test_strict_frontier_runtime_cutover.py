from __future__ import annotations

from types import SimpleNamespace

import apex_strong_boot as boot
import strict_frontier_preflight as preflight
from executable_frontier_authority import FrontierAuthorizationResult


def test_runtime_preflight_fails_closed_without_boot_receipt(monkeypatch) -> None:
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


def test_strong_boot_stops_before_model_attractor_when_strict_frontier_fails(
    monkeypatch,
) -> None:
    failures: list[str] = []
    result = FrontierAuthorizationResult(
        False,
        "frontier_authorization_unresolved",
        ("dependency enumeration missing",),
    )
    monkeypatch.setattr(boot, "validate_runtime_strict_frontier", lambda: result)

    def should_not_run():
        raise AssertionError("model-attractor preflight ran after strict frontier failure")

    monkeypatch.setattr(boot, "automatic_model_attractor_defense", should_not_run)
    boot._run_model_attractor_preflight(failures)
    assert failures == [
        "strict_executable_frontier_authority: dependency enumeration missing"
    ]


def test_strong_boot_runs_model_attractor_only_after_strict_frontier_authorizes(
    monkeypatch,
) -> None:
    failures: list[str] = []
    strict = FrontierAuthorizationResult(True, "frontier_authorized", ())
    validation = SimpleNamespace(ok=True, status="complete")
    calls: list[str] = []

    monkeypatch.setattr(boot, "validate_runtime_strict_frontier", lambda: strict)
    monkeypatch.setattr(
        boot, "get_in_process_model_attractor_validation", lambda: None
    )

    def automatic():
        calls.append("model-attractor")
        return validation

    monkeypatch.setattr(boot, "automatic_model_attractor_defense", automatic)
    monkeypatch.setattr(
        boot, "get_in_process_model_attractor_validation", lambda: validation
    )
    boot._run_model_attractor_preflight(failures)
    assert failures == []
    assert calls == ["model-attractor"]
