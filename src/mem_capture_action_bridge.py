"""Mem note -> existing APEX continuity ingest / native task provider adaptation.

Pure data transformation, no credentials or side effects. The caller owns source
validation, permission, reservation, native action, readback and Spiral journaling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA = "glaciereq.mem-capture-action/1.0"
WEEKDAYS = {name.lower(): index for index, name in enumerate((
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
))}
ACTION_RE = re.compile(
    r"^(Review|Check|Inspect|Audit|Verify|Prepare|Update|Follow up on|Test|Build|Fix|Remove|Repair|Execute|Implement|Integrate|Deploy|Ship|Enforce|Complete|Continue)\s+(.+?)(?:\s+on\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))?\.?$",
    re.IGNORECASE,
)


class CaptureRoutingError(ValueError):
    """An intake requires clarification, authorization or a source readback."""


@dataclass(frozen=True, slots=True)
class CaptureEnvelope:
    source_provider: str
    source_id: str
    source_version: int
    raw_text: str
    observed_at: str
    project: str
    sensitivity: str
    account_key: str
    timezone: str
    categories: tuple[str, ...]
    title: str | None
    due_date: str | None
    due_precision: str | None
    raw_sha256: str
    idempotency_key: str


def _required(value: Mapping[str, Any], key: str) -> str:
    field = value.get(key)
    if not isinstance(field, str) or not field.strip():
        raise CaptureRoutingError(f"{key} is required")
    return field.strip()


def build_capture(value: Mapping[str, Any]) -> CaptureEnvelope:
    """Classify a non-destructive intake; never infer a due time or an owner.

    The source note version and content are independent: source revisions are
    distinct APEX ingest events; the same semantic work has a stable action key.
    """
    if not isinstance(value, Mapping):
        raise CaptureRoutingError("capture must be a mapping")
    provider = _required(value, "source_provider").lower()
    if provider != "mem":
        raise CaptureRoutingError("only native Mem captures are supported")
    source_id = _required(value, "source_id")
    # Preserve the provider's exact source text: only test a trimmed view for validity.
    raw = value.get("raw_text")
    if not isinstance(raw, str) or not raw.strip():
        raise CaptureRoutingError("raw_text is required")
    observed = _required(value, "observed_at")
    project = _required(value, "project")
    sensitivity = _required(value, "sensitivity").lower()
    account_key = _required(value, "account_key")
    timezone_name = _required(value, "timezone")
    if value.get("source_version") is None:
        raise CaptureRoutingError("source_version is required")
    try:
        version = int(value.get("source_version"))
        zone = ZoneInfo(timezone_name)
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
        raise CaptureRoutingError("invalid version, observed timestamp or timezone") from exc
    if version < 1 or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise CaptureRoutingError("positive source version and offset-aware observed time required")

    local_day = observed_at.astimezone(zone).date()
    categories: tuple[str, ...] = ("REFERENCE",)
    title = due_date = due_precision = None
    match = ACTION_RE.fullmatch(raw.strip())
    if match:
        title = match.group(1) + " " + match.group(2).strip().rstrip(".")
        categories = ("ACTION", "COMMITMENT")
        if match.group(3):
            offset = (WEEKDAYS[match.group(3).lower()] - local_day.weekday()) % 7
            if offset != 0:  # bare weekday on the same day is ambiguous
                due_date = (local_day + timedelta(days=offset)).isoformat()
                due_precision = "day"
                categories += ("DEADLINE",)
    else:
        for prefix, kind in (("Decision:", "DECISION"), ("Correction:", "CORRECTION"),
                             ("Source:", "SOURCE"), ("Receipt:", "RECEIPT"),
                             ("Question:", "QUESTION")):
            if raw.lstrip().lower().startswith(prefix.lower()):
                categories = (kind,)
                break
    raw_hash = sha256(raw.encode("utf-8")).hexdigest()
    # Existing native owner task keys used the normalized text hash. Preserve
    # that legacy identity on replay while source evidence now stays verbatim.
    legacy_action_hash = sha256(raw.strip().encode("utf-8")).hexdigest()
    stable_input = json.dumps({
        "schema": SCHEMA, "source_provider": provider, "source_id": source_id,
        "raw_sha256": legacy_action_hash, "due_date": due_date, "project": project,
    }, sort_keys=True, separators=(",", ":"))
    action_key = "mem:" + sha256(stable_input.encode("utf-8")).hexdigest()
    return CaptureEnvelope(provider, source_id, version, raw, observed, project,
                           sensitivity, account_key, timezone_name, categories,
                           title, due_date, due_precision, raw_hash, action_key)


def _require_portable(item: CaptureEnvelope) -> None:
    if item.sensitivity != "non-sensitive":
        raise CaptureRoutingError("restricted or unclassified content cannot enter broad projections")


def make_ingest_rpc(item: CaptureEnvelope) -> dict[str, Any]:
    """Use existing APEX idempotent RPC, with version-aware external IDs."""
    _require_portable(item)
    return {
        "rpc": "continuity_ingest_and_resolve_v1",
        "rpc_executed": False,
        "external_action_authorized": False,
        "args": {
            "p_source_system": "mem",
            "p_account_key": item.account_key,
            "p_external_id": f"{item.source_id}:v{item.source_version}",
            "p_external_type": "capture",
            "p_occurred_at": item.observed_at,
            "p_payload": {
                "schema": SCHEMA,
                "source_provider": item.source_provider,
                "source_id": item.source_id,
                "source_version": item.source_version,
                "raw_text": item.raw_text,
                "raw_sha256": item.raw_sha256,
                "project": item.project,
                "sensitivity": item.sensitivity,
                "categories": list(item.categories),
                "due_date": item.due_date,
                "due_precision": item.due_precision,
                "timezone": item.timezone,
                "idempotency_key": item.idempotency_key,
            },
            "p_subject": item.title,
            "p_body": item.raw_text,
            "p_addresses": [],
            "p_phones": [],
            "p_external_ids": [],
        },
    }


def make_ticktick_task(item: CaptureEnvelope) -> dict[str, Any]:
    """Build a host-executable plan, not permission or proof of provider write."""
    _require_portable(item)
    if item.title is None:
        raise CaptureRoutingError("action title required for owner-native task")
    if item.due_date is not None and item.due_precision != "day":
        raise CaptureRoutingError("unsupported due-date precision for owner-native task")
    # An Operator action without a deadline is still actionable. Do not invent
    # a clock, date or reminder merely to satisfy a scheduling adapter.
    midnight = (
        datetime.combine(date.fromisoformat(item.due_date),
                         datetime.min.time(), tzinfo=ZoneInfo(item.timezone))
        if item.due_date is not None else None
    )
    return {
        "owner": "ticktick",
        "authorization_required": True,
        "external_action_executed": False,
        "idempotency_key": item.idempotency_key,
        "preflight": "search-existing-marker-and-reconcile-before-any-create",
        "ambiguous_timeout": "RECONCILE_PROVIDER_NEVER_BLIND_RETRY",
        "task": {
            "title": item.title,
            "content": (f"GlacierEQ Mem source {item.source_id}; "
                        f"capture_key={item.idempotency_key}; "
                        f"source_sha256={item.raw_sha256}; "
                        f"source_version={item.source_version}; "
                        f"due_precision={item.due_precision or 'unspecified'}; project={item.project}. "
                        "Controlled continuity test; no automatic mission completion."),
            **({"dueDate": midnight.isoformat()} if midnight is not None else {}),
            "timeZone": item.timezone,
            "isAllDay": midnight is not None,
            "status": 0,
            "kind": "TEXT",
        },
    }


def verify_ticktick_readback(item: CaptureEnvelope, response: Mapping[str, Any]) -> dict[str, Any]:
    """Evidence for this specific active-task test, not completed mission proof."""
    expected = make_ticktick_task(item)["task"]
    if not isinstance(response, Mapping):
        raise CaptureRoutingError("invalid provider readback")
    task_id = str(response.get("id") or "").strip()
    content = str(response.get("content") or "")
    if not task_id or response.get("title") != expected["title"]:
        raise CaptureRoutingError("owner ID or title mismatch")
    # Match complete provenance fields, not substrings of unrelated text.
    # A short source ID can otherwise appear inside a different ID or hash.
    canonical_source = f"GlacierEQ Mem source {item.source_id};"
    # Existing provider-native tasks used this explicit source label before
    # the newer canonical template. Accept both exact field labels, not loose IDs.
    legacy_source = f"Mem source note ID: {item.source_id};"
    correlation_fields = (
        f"capture_key={item.idempotency_key};",
        f"source_sha256={item.raw_sha256};",
        f"source_version={item.source_version};",
    )
    if not ((canonical_source in content or legacy_source in content)
            and all(marker in content for marker in correlation_fields)):
        raise CaptureRoutingError("provider task lacks exact source correlation")
    if response.get("timeZone") != item.timezone:
        raise CaptureRoutingError("provider task timezone conflict")
    if item.due_date is None:
        if response.get("dueDate") not in (None, ""):
            raise CaptureRoutingError("provider invented an unexpected due date")
        if response.get("isAllDay") not in (False, None):
            raise CaptureRoutingError("undated provider task cannot be all-day")
    else:
        if response.get("isAllDay") is not True:
            raise CaptureRoutingError("provider task day precision conflict")
        try:
            due = datetime.fromisoformat(str(response.get("dueDate", "")).replace("-1000", "-10:00"))
        except ValueError as exc:
            raise CaptureRoutingError("invalid provider due date") from exc
        if due.tzinfo is None or due.astimezone(ZoneInfo(item.timezone)).date().isoformat() != item.due_date:
            raise CaptureRoutingError("provider due date conflict")
    if response.get("status") != 0:
        raise CaptureRoutingError("provider task not in expected active state")
    return {
        "status": "OWNER_NATIVE_READBACK_VERIFIED",
        "owner": "ticktick",
        "provider_ref": task_id,
        "source_id": item.source_id,
        "source_version": item.source_version,
        "idempotency_key": item.idempotency_key,
        "provider_etag": response.get("etag"),
        "provider_status": 0,
        "due_date": item.due_date,
        "due_precision": "day",
        "completed": False,
        "mission_complete": False,
    }


def execute_authorized_capture(
    value: Mapping[str, Any],
    *,
    authorize: Any,
    ingest_rpc: Any,
    find_tasks: Any,
    create_task: Any,
    read_task: Any,
) -> dict[str, Any]:
    """Execute the existing Mem->APEX->TickTick route via native host callables.

    The caller supplies authenticated providers; the adapter never manufactures
    permission or receipts. Ambiguous writes are never retried blindly.
    """
    item = build_capture(value)
    plan = make_ingest_rpc(item)  # refuses broad projection of restricted content
    if authorize(item.source_id, "apex.ingest") is not True:
        raise CaptureRoutingError("source-scoped APEX ingest authority required")
    ingest = ingest_rpc(plan["rpc"], plan["args"])
    # Native APEX RPC returns {"ingest": {"ingest_id": ...}, "bound": ...};
    # preserve that exact provider envelope, rather than assuming a flat ID.
    native_ingest = ingest.get("ingest") if isinstance(ingest, Mapping) else None
    receipt_data = native_ingest if isinstance(native_ingest, Mapping) else ingest
    if not isinstance(receipt_data, Mapping) or not (
        receipt_data.get("id") or receipt_data.get("ingest_id")
        or receipt_data.get("receipt_id")
    ):
        raise CaptureRoutingError("APEX RPC returned no provider receipt")
    result = {
        "source_id": item.source_id,
        "source_version": item.source_version,
        "ingest_receipt": dict(ingest),
        "mission_complete": False,
    }
    if item.title is None:
        result["owner_status"] = "NO_ACTION"
        return result
    if authorize(item.source_id, "ticktick.task") is not True:
        result["owner_status"] = "TASK_AUTHORITY_REQUIRED"
        return result
    task_plan = make_ticktick_task(item)
    existing = find_tasks(item.idempotency_key)
    if not isinstance(existing, list):
        raise CaptureRoutingError("native task preflight must return a list")
    if len(existing) > 1:
        raise CaptureRoutingError("ambiguous duplicate tasks; reconcile before create")
    if existing:
        task_id = str(existing[0].get("id") or "").strip()
        if not task_id:
            raise CaptureRoutingError("preflight match lacks native task ID")
        operation = "reused"
    else:
        created = create_task(task_plan["task"])
        if not isinstance(created, Mapping) or not created.get("id"):
            raise CaptureRoutingError("task create returned no native ID; reconcile before retry")
        task_id = str(created["id"])
        operation = "created"
    # A separately fetched provider object is required, not the optimistic write response.
    readback = read_task(task_id)
    result["task_receipt"] = verify_ticktick_readback(item, readback)
    result["owner_operation"] = operation
    result["owner_status"] = "OWNER_NATIVE_READBACK_VERIFIED"
    return result
