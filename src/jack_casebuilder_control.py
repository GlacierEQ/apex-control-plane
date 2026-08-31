from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

CASE_GRAPH_SCHEMA = "casebuilder4000.case-graph.v2"
CONVERSION_SCHEMA = "casebuilder4000.conversion-bundle.v2"
BUILD_RECEIPT_SCHEMA = "casebuilder4000.build-receipt.v2"

ALLOWED_NODE_TYPES = {
    "CASE",
    "SOURCE",
    "SOURCE_ROOT",
    "DOCKET",
    "ACTOR",
    "EVENT",
    "COMMUNICATION",
    "EVIDENCE",
    "AUTHORITY",
    "FACT",
    "ELEMENT",
    "ALLEGATION",
    "THEORY",
    "CONTRADICTION",
    "KNOWLEDGE",
    "PATTERN",
    "DEFENSE",
    "REBUTTAL",
    "CAUSATION",
    "HARM",
    "DISCOVERY_TARGET",
    "REMEDY",
    "ACCOUNTABILITY_PATH",
    "ATTACK",
    "DEADLINE",
    "FILING_PARAGRAPH",
    "CROSS_EXAM",
}


class JackCasebuilderContractError(ValueError):
    """Raised when a Casebuilder projection violates the control-plane contract."""


class DispatchPlane(Protocol):
    def dispatch(self, job_cost: int = 1, capability: str | None = None) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class JackJob:
    job_id: str
    case_id: str
    object_id: str
    object_type: str
    capability: str
    priority: int
    action: str
    reason: str
    external_action_authorized: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "case_id": self.case_id,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "capability": self.capability,
            "priority": self.priority,
            "action": self.action,
            "reason": self.reason,
            "external_action_authorized": self.external_action_authorized,
        }


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def validate_case_graph(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if payload.get("schema") != CASE_GRAPH_SCHEMA:
        raise JackCasebuilderContractError(
            f"case graph schema must be {CASE_GRAPH_SCHEMA}"
        )
    case_id = str(payload.get("case_id") or "").strip()
    if not case_id:
        raise JackCasebuilderContractError("case graph requires case_id")

    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise JackCasebuilderContractError("case graph requires nodes and edges arrays")

    nodes: dict[str, Mapping[str, Any]] = {}
    case_nodes = 0
    for index, row in enumerate(raw_nodes):
        if not isinstance(row, Mapping):
            raise JackCasebuilderContractError(f"nodes[{index}] must be an object")
        node_id = str(row.get("id") or "").strip()
        node_type = str(row.get("type") or "").strip()
        label = str(row.get("label") or "").strip()
        if not node_id or not label:
            raise JackCasebuilderContractError(f"nodes[{index}] requires id and label")
        if node_type not in ALLOWED_NODE_TYPES:
            raise JackCasebuilderContractError(
                f"nodes[{index}] unsupported type: {node_type}"
            )
        if node_id in nodes:
            raise JackCasebuilderContractError(f"duplicate case graph node: {node_id}")
        nodes[node_id] = row
        if node_type == "CASE":
            case_nodes += 1
            if node_id != case_id:
                raise JackCasebuilderContractError(
                    "CASE node id must equal case graph case_id"
                )

    if case_nodes != 1:
        raise JackCasebuilderContractError(
            f"case graph requires exactly one CASE node, found {case_nodes}"
        )

    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, Mapping):
            raise JackCasebuilderContractError(f"edges[{index}] must be an object")
        source = str(edge.get("from") or "").strip()
        target = str(edge.get("to") or "").strip()
        relation = str(edge.get("type") or "").strip()
        if not source or not target or not relation:
            raise JackCasebuilderContractError(
                f"edges[{index}] requires from, to, and type"
            )
        if source not in nodes:
            raise JackCasebuilderContractError(
                f"edges[{index}] references missing source node {source}"
            )
        if target not in nodes:
            raise JackCasebuilderContractError(
                f"edges[{index}] references missing target node {target}"
            )
    return nodes


def validate_bundle(
    graph: Mapping[str, Any],
    *,
    conversion: Mapping[str, Any] | None = None,
    build_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = validate_case_graph(graph)
    case_id = str(graph["case_id"])

    if conversion is not None:
        if conversion.get("schema") != CONVERSION_SCHEMA:
            raise JackCasebuilderContractError(
                f"conversion schema must be {CONVERSION_SCHEMA}"
            )
        if conversion.get("case_id") != case_id:
            raise JackCasebuilderContractError(
                "conversion bundle case_id does not match case graph"
            )

    if build_receipt is not None:
        if build_receipt.get("schema") != BUILD_RECEIPT_SCHEMA:
            raise JackCasebuilderContractError(
                f"build receipt schema must be {BUILD_RECEIPT_SCHEMA}"
            )
        if build_receipt.get("case_id") != case_id:
            raise JackCasebuilderContractError(
                "build receipt case_id does not match case graph"
            )
        if build_receipt.get("validation_errors") not in ([], None):
            raise JackCasebuilderContractError(
                "casebuilder build receipt contains validation errors"
            )

    return {
        "case_id": case_id,
        "node_count": len(nodes),
        "edge_count": len(graph.get("edges", [])),
        "graph_sha256": _sha256(graph),
        "conversion_sha256": _sha256(conversion) if conversion is not None else None,
        "build_receipt_sha256": (
            _sha256(build_receipt) if build_receipt is not None else None
        ),
    }


def _priority(value: object, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def compile_jack_execution_queue(
    graph: Mapping[str, Any],
    *,
    conversion: Mapping[str, Any] | None = None,
) -> list[JackJob]:
    nodes = validate_case_graph(graph)
    case_id = str(graph["case_id"])
    jobs: list[JackJob] = []

    def add(
        node_id: str,
        node_type: str,
        capability: str,
        priority: int,
        action: str,
        reason: str,
    ) -> None:
        jobs.append(
            JackJob(
                job_id=f"JACK::{case_id}::{capability}::{node_id}",
                case_id=case_id,
                object_id=node_id,
                object_type=node_type,
                capability=capability,
                priority=_priority(priority, 50),
                action=action,
                reason=reason,
            )
        )

    for node_id, node in nodes.items():
        node_type = str(node["type"])
        if node_type == "DISCOVERY_TARGET":
            add(
                node_id,
                node_type,
                "legal_discovery",
                _priority(node.get("priority"), 90),
                "develop_and_route_targeted_record_acquisition",
                str(node.get("label") or "material evidence target"),
            )
        elif node_type == "ELEMENT":
            state = str(node.get("state") or "").casefold()
            if state in {"missing", "disputed", "legal_defect"}:
                add(
                    node_id,
                    node_type,
                    "legal_element_development",
                    100 if state == "legal_defect" else 95 if state == "missing" else 85,
                    "resolve_element_support_or_legal_defect",
                    f"element state is {state}",
                )
        elif node_type == "CONTRADICTION":
            status = str(node.get("status") or "open").casefold()
            if status not in {"resolved", "immaterial", "closed"}:
                add(
                    node_id,
                    node_type,
                    "contradiction_resolution",
                    90,
                    "resolve_material_conflict_and_preserve_impeachment_value",
                    f"contradiction status is {status}",
                )
        elif node_type == "ALLEGATION":
            status = str(node.get("status") or "").casefold()
            tier = _priority(node.get("tier"), 5)
            if status in {"raw", "structured", "sourced", "corroborated", "element_mapped"}:
                add(
                    node_id,
                    node_type,
                    "allegation_hardening",
                    92 if tier <= 2 else 82,
                    "run_proof_stack_kill_test_defense_and_gap_hardening",
                    f"allegation status is {status}, tier {tier}",
                )
            elif status in {"defense_tested", "hardened"}:
                add(
                    node_id,
                    node_type,
                    "legal_conversion",
                    88 if tier <= 2 else 76,
                    "convert_hardened_allegation_to_downstream_work_products",
                    f"allegation is {status}, tier {tier}",
                )
        elif node_type in {"EVIDENCE", "SOURCE", "SOURCE_ROOT"}:
            fact_state = str(node.get("fact_state") or "").casefold()
            if any(token in fact_state for token in ("unresolved", "contradict", "derivative")):
                add(
                    node_id,
                    node_type,
                    "evidence_integrity",
                    86,
                    "resolve_source_provenance_authentication_or_conflict",
                    f"evidence/source state is {fact_state or 'unresolved'}",
                )
        elif node_type == "AUTHORITY":
            add(
                node_id,
                node_type,
                "legal_authority_mapping",
                82,
                "map_controlling_authority_to_case_elements_and_dates",
                str(node.get("label") or "authority node"),
            )
        elif node_type == "ATTACK":
            add(
                node_id,
                node_type,
                "legal_attack_development",
                78,
                "bind_attack_to_surviving_allegations_elements_sources_and_remedies",
                str(node.get("label") or "attack node"),
            )
        elif node_type == "DEFENSE":
            add(
                node_id,
                node_type,
                "defense_testing",
                84,
                "attack_strongest_defense_and_bind_rebuttal_support",
                str(node.get("label") or "defense node"),
            )
        elif node_type == "REBUTTAL":
            add(
                node_id,
                node_type,
                "rebuttal_hardening",
                82,
                "source_lock_rebuttal_and_residual_risk",
                str(node.get("label") or "rebuttal node"),
            )
        elif node_type == "CAUSATION":
            add(
                node_id,
                node_type,
                "causation_development",
                80,
                "trace_act_to_immediate_effect_to_decision_to_harm",
                str(node.get("label") or "causation node"),
            )
        elif node_type == "REMEDY":
            add(
                node_id,
                node_type,
                "remedy_projection",
                74,
                "map_remedy_prerequisites_authority_and_supported_allegations",
                str(node.get("label") or "remedy node"),
            )
        elif node_type == "DEADLINE":
            add(
                node_id,
                node_type,
                "deadline_review",
                98,
                "verify_deadline_source_and_bind_to_required_case_action",
                str(node.get("label") or "deadline node"),
            )
        elif node_type == "HARM":
            add(
                node_id,
                node_type,
                "damage_development",
                70,
                "trace_causation_amount_and_source_support",
                str(node.get("label") or "harm requires damage-chain development"),
            )
        elif node_type == "ACCOUNTABILITY_PATH":
            add(
                node_id,
                node_type,
                "accountability_projection",
                75,
                "map_prerequisites_authority_and_remedy_path",
                str(node.get("label") or "accountability path"),
            )
        elif node_type == "CROSS_EXAM":
            add(
                node_id,
                node_type,
                "cross_exam_generation",
                68,
                "compile_source_locked_question_sequence",
                str(node.get("label") or "cross-examination block"),
            )

    if conversion is not None:
        if conversion.get("schema") != CONVERSION_SCHEMA:
            raise JackCasebuilderContractError(
                f"conversion schema must be {CONVERSION_SCHEMA}"
            )
        if conversion.get("case_id") != case_id:
            raise JackCasebuilderContractError(
                "conversion bundle case_id does not match case graph"
            )
        for name, capability, priority in (
            ("pleading_map", "pleading_projection", 86),
            ("motion_map", "motion_projection", 84),
            ("referral_map", "referral_projection", 80),
            ("discovery_map", "discovery_projection", 88),
            ("cross_exam_map", "cross_exam_projection", 72),
        ):
            rows = conversion.get(name, [])
            if not isinstance(rows, list):
                raise JackCasebuilderContractError(f"{name} must be an array")
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    raise JackCasebuilderContractError(
                        f"{name}[{index}] must be an object"
                    )
                object_id = str(
                    row.get("allegation_id")
                    or row.get("id")
                    or f"{name}-{index:04d}"
                )
                add(
                    object_id,
                    "CONVERSION",
                    capability,
                    priority,
                    f"materialize_{name.removesuffix('_map')}",
                    f"{name} contains a conversion-ready object",
                )

    dedup: dict[str, JackJob] = {}
    for job in jobs:
        prior = dedup.get(job.job_id)
        if prior is None or job.priority > prior.priority:
            dedup[job.job_id] = job
    return sorted(
        dedup.values(),
        key=lambda job: (-job.priority, job.capability, job.object_id),
    )


def dispatch_jack_queue(
    control_plane: DispatchPlane,
    jobs: Sequence[JackJob],
) -> list[dict[str, Any]]:
    """Dispatch internal work only; no external provider action is authorized."""
    receipts: list[dict[str, Any]] = []
    for job in jobs:
        dispatch = dict(control_plane.dispatch(1, capability=job.capability))
        receipts.append(
            {
                "job": job.as_dict(),
                "dispatch": dispatch,
                "external_action_authorized": False,
            }
        )
    return receipts


def build_control_plane_receipt(
    graph: Mapping[str, Any],
    *,
    conversion: Mapping[str, Any] | None = None,
    build_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validated = validate_bundle(
        graph,
        conversion=conversion,
        build_receipt=build_receipt,
    )
    queue = compile_jack_execution_queue(graph, conversion=conversion)
    body = {
        "schema": "glaciereq.jack-casebuilder-control-receipt.v1",
        **validated,
        "job_count": len(queue),
        "capabilities": sorted({job.capability for job in queue}),
        "jobs": [job.as_dict() for job in queue],
        "external_action_authorized": False,
    }
    return {
        **body,
        "receipt_sha256": _sha256(body),
    }
