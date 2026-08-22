#!/usr/bin/env python3
"""Validate APEX legal packets for structural and cross-reference integrity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

COLLECTIONS = (
    "allegations", "evidence", "chronology", "contradictions", "authorities",
    "actors", "remedies", "proof_gaps", "preservation_targets",
)


def finding(level: str, code: str, path: str, message: str) -> tuple[str, str, str, str]:
    return level, code, path, message


def validate(packet: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    indexes: dict[str, dict[str, dict[str, Any]]] = {}

    for key in ("matter_id", "generated_at"):
        if not isinstance(packet.get(key), str) or not packet[key].strip():
            out.append(finding("ERROR", "MISSING_REQUIRED", key, "must be a non-empty string"))

    for collection in COLLECTIONS:
        items = packet.get(collection, [])
        if not isinstance(items, list):
            out.append(finding("ERROR", "INVALID_COLLECTION", collection, "must be an array"))
            continue
        index: dict[str, dict[str, Any]] = {}
        for pos, item in enumerate(items):
            path = f"{collection}[{pos}]"
            if not isinstance(item, dict):
                out.append(finding("ERROR", "INVALID_OBJECT", path, "must be an object"))
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                out.append(finding("ERROR", "MISSING_ID", path, "non-empty id required"))
                continue
            if item_id in index:
                out.append(finding("ERROR", "DUPLICATE_ID", f"{path}.id", item_id))
                continue
            index[item_id] = item
        indexes[collection] = index

    def refs(path: str, values: Any, target: str) -> None:
        if values is None:
            return
        if not isinstance(values, list):
            out.append(finding("ERROR", "INVALID_REF_LIST", path, "must be an array of ids"))
            return
        for pos, ref in enumerate(values):
            if not isinstance(ref, str) or ref not in indexes.get(target, {}):
                out.append(finding("ERROR", "BROKEN_REFERENCE", f"{path}[{pos}]", f"{ref!r} not in {target}"))

    for aid, allegation in indexes.get("allegations", {}).items():
        base = f"allegations[{aid}]"
        if not isinstance(allegation.get("label"), str) or not allegation["label"].strip():
            out.append(finding("ERROR", "MISSING_LABEL", f"{base}.label", "allegation label required"))
        elements = allegation.get("elements")
        if not isinstance(elements, list) or not elements:
            out.append(finding("ERROR", "MISSING_ELEMENTS", f"{base}.elements", "at least one legal element required"))
        else:
            for pos, element in enumerate(elements):
                ep = f"{base}.elements[{pos}]"
                if not isinstance(element, dict) or not isinstance(element.get("name"), str) or not element["name"].strip():
                    out.append(finding("ERROR", "INVALID_ELEMENT", ep, "named element object required"))
                    continue
                refs(f"{ep}.supporting_evidence_ids", element.get("supporting_evidence_ids", []), "evidence")
                refs(f"{ep}.contrary_evidence_ids", element.get("contrary_evidence_ids", []), "evidence")
                refs(f"{ep}.proof_gap_ids", element.get("proof_gap_ids", []), "proof_gaps")
        refs(f"{base}.evidence_ids", allegation.get("evidence_ids", []), "evidence")
        refs(f"{base}.actor_ids", allegation.get("actor_ids", []), "actors")
        refs(f"{base}.authority_ids", allegation.get("authority_ids", []), "authorities")
        refs(f"{base}.remedy_ids", allegation.get("remedy_ids", []), "remedies")
        refs(f"{base}.event_ids", allegation.get("event_ids", []), "chronology")

    for eid, event in indexes.get("chronology", {}).items():
        base = f"chronology[{eid}]"
        refs(f"{base}.actor_ids", event.get("actor_ids", []), "actors")
        refs(f"{base}.source_evidence_ids", event.get("source_evidence_ids", []), "evidence")
        if event.get("time_basis") == "EXACT" and not event.get("timestamp"):
            out.append(finding("ERROR", "EXACT_TIME_NO_TIMESTAMP", f"{base}.timestamp", "EXACT requires timestamp"))
        if event.get("time_basis") in (None, "UNKNOWN"):
            out.append(finding("WARN", "WEAK_TEMPORAL_PRECISION", f"{base}.time_basis", "timing unresolved"))

    evidence = indexes.get("evidence", {})
    for cid, contradiction in indexes.get("contradictions", {}).items():
        for field in ("left_source_id", "right_source_id"):
            ref = contradiction.get(field)
            if not isinstance(ref, str) or ref not in evidence:
                out.append(finding("ERROR", "BROKEN_CONTRADICTION_SOURCE", f"contradictions[{cid}].{field}", repr(ref)))

    for authid, authority in indexes.get("authorities", {}).items():
        base = f"authorities[{authid}]"
        if authority.get("verified") is not True:
            out.append(finding("WARN", "UNVERIFIED_AUTHORITY", f"{base}.verified", "verify primary authority"))
        if authority.get("temporal_fit") in (None, "UNKNOWN"):
            out.append(finding("WARN", "UNKNOWN_TEMPORAL_FIT", f"{base}.temporal_fit", "verify law/rule version governing event"))

    for actorid, actor in indexes.get("actors", {}).items():
        base = f"actors[{actorid}]"
        refs(f"{base}.event_ids", actor.get("event_ids", []), "chronology")
        refs(f"{base}.evidence_ids", actor.get("evidence_ids", []), "evidence")
        if not actor.get("responsibility_modes"):
            out.append(finding("WARN", "UNMAPPED_RESPONSIBILITY", f"{base}.responsibility_modes", "map responsibility chain"))

    for rid, remedy in indexes.get("remedies", {}).items():
        base = f"remedies[{rid}]"
        refs(f"{base}.authority_ids", remedy.get("authority_ids", []), "authorities")
        refs(f"{base}.allegation_ids", remedy.get("allegation_ids", []), "allegations")

    for gid, gap in indexes.get("proof_gaps", {}).items():
        if not gap.get("target"):
            out.append(finding("WARN", "NO_ACQUISITION_TARGET", f"proof_gaps[{gid}].target", "map to retrieval/discovery/preservation/authority check"))

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an APEX legal analysis packet")
    parser.add_argument("packet", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat warnings as failure")
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR PACKET_LOAD {args.packet}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(packet, dict):
        print("ERROR PACKET_LOAD top-level packet must be a JSON object", file=sys.stderr)
        return 2
    findings = validate(packet)
    for level, code, path, message in findings:
        print(f"{level:<5} {code:<28} {path}: {message}")
    errors = sum(level == "ERROR" for level, *_ in findings)
    warnings = sum(level == "WARN" for level, *_ in findings)
    print(f"SUMMARY errors={errors} warnings={warnings}")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
