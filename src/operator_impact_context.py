"""Impact-weighted operator context loaded at the earliest user-controlled runtime boundary.

This module is intentionally lightweight and network-free. Python startup can load it
without depending on Supabase availability. A local profile is the immediate projection;
Supabase remains the durable/live refresh source through the operator-impact-context
Edge Function.

This context never overrides platform/system/developer instructions. It supplies
operator interpretation where runtime judgment is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PROFILE = _REPO_ROOT / "OPERATOR_RUNTIME" / "impact_weighted_decision_profile.json"

_DEFAULT_PRINCIPLE = (
    "Always evaluate everything relevant to the actual situation. "
    "Analyze impact first; rules are weighted inputs, not substitutes for judgment."
)

_DEFAULT_FACTORS = (
    "objective_fit",
    "failure_impact",
    "victory_impact",
    "urgency",
    "delay_cost",
    "reversibility",
    "downside_severity",
    "uncertainty",
    "evidence_access",
    "source_relevance",
    "strategic_leverage",
    "undershoot_risk",
    "overshoot_risk",
    "second_order_effects",
    "prior_rule_fit",
)


@dataclass(frozen=True, slots=True)
class OperatorImpactContext:
    profile_key: str
    operator: str
    principle: str
    factors: tuple[str, ...]
    source_routing: Mapping[str, str]
    recompute_on: tuple[str, ...]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_key": self.profile_key,
            "operator": self.operator,
            "principle": self.principle,
            "factors": list(self.factors),
            "source_routing": dict(self.source_routing),
            "recompute_on": list(self.recompute_on),
            "source": self.source,
        }


def _load_payload(path: Path) -> tuple[dict[str, Any], str]:
    injected = os.getenv("GLACIEREQ_IMPACT_CONTEXT_JSON", "").strip()
    if injected:
        try:
            payload = json.loads(injected)
            if isinstance(payload, dict):
                if isinstance(payload.get("profile"), dict):
                    payload = payload["profile"]
                return payload, "environment_projection"
        except json.JSONDecodeError:
            pass

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload, f"local:{path}"
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    return {}, "built_in_fallback"


def load_operator_impact_context(
    path: str | Path | None = None,
) -> OperatorImpactContext:
    target = Path(path).expanduser().resolve() if path else _DEFAULT_PROFILE
    payload, source = _load_payload(target)

    routing = payload.get("source_routing")
    if not isinstance(routing, dict):
        routing = {}

    factors = payload.get("factors")
    if not isinstance(factors, list) or not all(isinstance(v, str) for v in factors):
        factors = list(_DEFAULT_FACTORS)

    recompute = payload.get("recompute_on")
    if not isinstance(recompute, list) or not all(isinstance(v, str) for v in recompute):
        recompute = [
            "material context change",
            "new evidence",
            "new deadline",
            "new irreversible consequence",
            "connector health change",
            "operator correction",
        ]

    context = OperatorImpactContext(
        profile_key=str(payload.get("profile_key") or "casey_impact_weighted_v1"),
        operator=str(payload.get("operator") or "Casey Barton / GlacierEQ"),
        principle=str(payload.get("principle") or _DEFAULT_PRINCIPLE),
        factors=tuple(factors),
        source_routing=MappingProxyType({str(k): str(v) for k, v in routing.items()}),
        recompute_on=tuple(recompute),
        source=source,
    )

    os.environ["GLACIEREQ_IMPACT_CONTEXT_STATUS"] = "loaded"
    os.environ["GLACIEREQ_IMPACT_PROFILE_KEY"] = context.profile_key
    os.environ["GLACIEREQ_IMPACT_CONTEXT_SOURCE"] = context.source
    return context


OPERATOR_IMPACT_CONTEXT = load_operator_impact_context()
