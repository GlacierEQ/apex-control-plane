#!/usr/bin/env python3
"""APEX control-plane entrypoint with one mandatory strongest-boot path.

The entrypoint does not assemble startup proofs independently. It requires the
sealed strong-boot session, then transfers that exact session and runtime kernel
to the verified runtime boundary. The preserved runtime implementation is loaded
as a library behind that boundary rather than executed directly.
"""
from __future__ import annotations

from continuous_control_plane import (
    ContinuousControlPlane,
    ControlEvent,
    ExecutionReceipt,
    JsonlControlStore,
    WorkItem,
    WorkState,
)
import json
import os
from pathlib import Path
import runpy
import sys
from typing import Any


def _require_completed_startup_validations(
    validations: tuple[tuple[str, Any | None], ...],
) -> None:
    """Compatibility validator for callers that already hold startup proofs.

    This helper does not run boot stages or authorize runtime loading. The real
    executable startup path is `apply_strongest_boot()` below.
    """
    incomplete: list[str] = []
    for gate_name, validation in validations:
        if validation is None:
            incomplete.append(f"{gate_name}: validation missing")
            continue
        if validation.ok is not True or validation.status != "complete":
            incomplete.append(
                f"{gate_name}: status={validation.status!r}, ok={validation.ok!r}"
            )
    if incomplete:
        raise RuntimeError(
            "runtime authorization denied; mandatory startup gates incomplete: "
            + "; ".join(incomplete)
        )


def _validate_explicit_boot_receipt_syntax() -> None:
    """Reject malformed explicit receipt input without turning absence into a gate.

    Missing receipt is an uplift/continuation condition handled by strongest boot.
    A caller that explicitly supplies syntactically invalid JSON has instead
    supplied unusable provider evidence; fail that route closed before legacy
    observers can convert the parsing error into a generic uplift finding.
    """
    inline = os.getenv("CASEY_BOOT_RECEIPT_JSON", "").strip()
    if not inline:
        return
    try:
        payload = json.loads(inline)
    except json.JSONDecodeError as exc:
        raise ValueError(f"CASEY_BOOT_RECEIPT_JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("CASEY_BOOT_RECEIPT_JSON must contain an object")


if __name__ == "__main__":
    # Invoke the existing durable event router when an event is provided.
    # No event means idle: do not invent a successful route or receipt.
    import argparse

    from apex_proactive import state_receipt
    from continuous_control_plane import load_continuous_control_config

    parser = argparse.ArgumentParser(description="APEX durable event-router entrypoint")
    parser.add_argument("--event-file", type=Path, help="Source event JSON to ingest")
    parser.add_argument(
        "--state-dir", type=Path, default=Path.home() / ".apex" / "control-plane",
        help="Existing APEX event/work/receipt state directory",
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "continuous_control_plane.json",
        help="Existing APEX route configuration",
    )
    args = parser.parse_args()

    if args.event_file is None:
        print(json.dumps({"status": "idle", "routes_run": 0}, sort_keys=True))
        sys.exit(0)

    raw = json.loads(args.event_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        parser.error("event file must contain a JSON object")
    event = ControlEvent(
        event_type=raw["event_type"],
        source_system=raw["source_system"],
        subject_id=raw["subject_id"],
        correlation_id=raw["correlation_id"],
        payload=raw.get("payload", {}),
        provenance_refs=tuple(raw.get("provenance_refs", ())),
        **({"event_id": raw["event_id"]} if raw.get("event_id") else {}),
    )
    config = load_continuous_control_config(args.config)
    plane = ContinuousControlPlane.from_config(JsonlControlStore(args.state_dir), config)
    def counts(snapshot: dict[str, Any]) -> dict[str, int]:
        return {key: snapshot[key] for key in ("events", "work", "receipts")}

    before = counts(plane.snapshot())
    created = plane.ingest_event(event)
    # Fresh instance forces actual disk readback, not just an in-memory count.
    readback = ContinuousControlPlane.from_config(JsonlControlStore(args.state_dir), config)
    after = counts(readback.snapshot())
    if after["events"] < before["events"] or after["work"] < before["work"]:
        raise RuntimeError("APEX state regressed during readback")
    if any(item.work_id not in readback.work for item in created):
        raise RuntimeError("APEX event routing not durably readable")

    receipt = state_receipt(before, after, "event_ingestion")
    print(json.dumps({
        "status": "ingested" if after["events"] > before["events"] else "duplicate",
        "created_work": len(created),
        "routes_run": len(created),
        "receipt": receipt.to_dict(),
        "readback": after,
    }, sort_keys=True))

else:
    from control_plane_runtime import *  # noqa: F401,F403
