"""Persistent mission ambition for APEX.

Ambition is not rhetoric. It is accumulated execution pressure created when the
same mission is selected repeatedly without a material state transition.

The controller is domain-neutral. It does not grant authority, relax evidence
requirements, or convert activity into progress. It simply makes stagnation
increasingly expensive in action ranking until the mission changes or a genuine
external boundary is established.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


class AmbitionLevel(str, Enum):
    STEADY = "steady"
    PUSH = "push"
    DRIVE = "drive"
    RELENTLESS = "relentless"
    BREAKTHROUGH = "breakthrough"


@dataclass(frozen=True, slots=True)
class AmbitionPressure:
    level: AmbitionLevel
    score: float
    nonprogress_streak: int
    verified_progress_count: int
    mission_key: str

    @property
    def active(self) -> bool:
        return self.nonprogress_streak > 0


@dataclass(slots=True)
class _MissionState:
    mission_key: str
    operation_class: str
    nonprogress_streak: int = 0
    verified_progress_count: int = 0
    last_state_version: str | None = None
    last_material_state_version: str | None = None
    last_reason: str = ""


class MissionAmbition:
    """Track and persist mission drive across repeated execution attempts."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self.state_path = Path(state_path).expanduser() if state_path else None
        self._states: dict[str, _MissionState] = {}
        self._load()

    def observe_selection(
        self,
        *,
        mission: str,
        operation_class: str,
        state_version: str,
    ) -> AmbitionPressure:
        state = self._state(mission, operation_class)
        version = _required(state_version, "state_version")
        if state.last_state_version == version:
            state.nonprogress_streak += 1
            state.last_reason = "reselected_without_state_change"
        elif state.last_state_version is not None:
            # A changed observed state is movement, but only an explicit verified
            # mission outcome fully resets accumulated pressure.
            state.nonprogress_streak = max(0, state.nonprogress_streak - 1)
            state.last_reason = "observed_state_changed"
        state.last_state_version = version
        self._save()
        return self._pressure(state)

    def record_outcome(
        self,
        *,
        mission: str,
        operation_class: str,
        state_version: str,
        material_progress: bool,
        reason: str,
    ) -> AmbitionPressure:
        state = self._state(mission, operation_class)
        version = _required(state_version, "state_version")
        state.last_state_version = version
        state.last_reason = _required(reason, "reason")
        if material_progress:
            state.verified_progress_count += 1
            state.nonprogress_streak = 0
            state.last_material_state_version = version
        else:
            state.nonprogress_streak += 1
        self._save()
        return self._pressure(state)

    def pressure_for(
        self, *, mission: str, operation_class: str
    ) -> AmbitionPressure:
        return self._pressure(self._state(mission, operation_class))

    def snapshot(self, *, mission: str, operation_class: str) -> Mapping[str, Any]:
        state = self._state(mission, operation_class)
        pressure = self._pressure(state)
        return {
            **asdict(state),
            "level": pressure.level.value,
            "score": pressure.score,
        }

    def _state(self, mission: str, operation_class: str) -> _MissionState:
        mission_text = _required(mission, "mission")
        operation = _required(operation_class, "operation_class")
        key = _mission_key(mission_text, operation)
        state = self._states.get(key)
        if state is None:
            state = _MissionState(mission_key=key, operation_class=operation)
            self._states[key] = state
        return state

    @staticmethod
    def _pressure(state: _MissionState) -> AmbitionPressure:
        streak = max(0, int(state.nonprogress_streak))
        score = min(1.0, streak / 4.0)
        if streak == 0:
            level = AmbitionLevel.STEADY
        elif streak == 1:
            level = AmbitionLevel.PUSH
        elif streak == 2:
            level = AmbitionLevel.DRIVE
        elif streak == 3:
            level = AmbitionLevel.RELENTLESS
        else:
            level = AmbitionLevel.BREAKTHROUGH
        return AmbitionPressure(
            level=level,
            score=score,
            nonprogress_streak=streak,
            verified_progress_count=state.verified_progress_count,
            mission_key=state.mission_key,
        )

    def _load(self) -> None:
        if self.state_path is None or not self.state_path.is_file():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key, row in dict(payload.get("missions", {})).items():
            if not isinstance(row, Mapping):
                continue
            try:
                self._states[str(key)] = _MissionState(
                    mission_key=str(row["mission_key"]),
                    operation_class=str(row["operation_class"]),
                    nonprogress_streak=max(0, int(row.get("nonprogress_streak", 0))),
                    verified_progress_count=max(
                        0, int(row.get("verified_progress_count", 0))
                    ),
                    last_state_version=_optional_text(row.get("last_state_version")),
                    last_material_state_version=_optional_text(
                        row.get("last_material_state_version")
                    ),
                    last_reason=str(row.get("last_reason", "")),
                )
            except (KeyError, TypeError, ValueError):
                continue

    def _save(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "missions": {
                key: asdict(state) for key, state in sorted(self._states.items())
            },
        }
        target = self.state_path
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(target)


def ambition_adjusted_features(
    features: Mapping[str, float],
    *,
    metadata: Mapping[str, Any],
    pressure: AmbitionPressure,
) -> dict[str, float]:
    """Add candidate-specific drive and stagnation signals to ranking."""
    adjusted = {str(k): _clamp01(float(v)) for k, v in features.items()}
    if not pressure.active:
        adjusted.setdefault("ambition_drive", 0.0)
        adjusted.setdefault("stagnation_risk", 0.0)
        return adjusted

    advancement = adjusted.get("mission_advancement", 0.0)
    state_change = adjusted.get("state_change_value", 0.0)
    proximity = adjusted.get("execution_proximity", 0.0)
    directness = _clamp01(
        0.40 * advancement + 0.35 * state_change + 0.25 * proximity
    )

    meta = adjusted.get("meta_substitution_risk", 0.0)
    rediscovery = adjusted.get("rediscovery_risk", 0.0)
    already_done = adjusted.get("already_done_risk", 0.0)
    rule_accretion = adjusted.get("rule_accretion_risk", 0.0)
    stagnation = _clamp01(
        0.30 * meta
        + 0.30 * rediscovery
        + 0.25 * already_done
        + 0.15 * rule_accretion
    )

    if bool(metadata.get("activity_only")):
        stagnation = max(stagnation, 0.85)
    if bool(metadata.get("material_state_change")):
        directness = max(directness, 0.90)

    adjusted["ambition_drive"] = _clamp01(pressure.score * directness)
    adjusted["stagnation_risk"] = _clamp01(pressure.score * stagnation)
    return adjusted


def _mission_key(mission: str, operation_class: str) -> str:
    raw = f"{operation_class}\n{mission}".encode("utf-8")
    return sha256(raw).hexdigest()


def _required(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
