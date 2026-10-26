"""Direct execution path for Operator-authorized work.

Internal work executes without boot, completeness, or provider-admission gates.
Only an actual external effect requires an authority callback and native readback.
SQLite makes reservations durable; a possible side effect is never blindly replayed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Callable, Mapping, Sequence


class ExecutionDenied(RuntimeError):
    """Operation is invalid, changed, or lacks the authority for this effect."""


class ReconciliationRequired(RuntimeError):
    """A previous or current effect may have happened; read provider state first."""


@dataclass(frozen=True)
class Action:
    mission_id: str
    operation_id: str
    kind: str
    payload: Mapping[str, Any]
    external: bool = False
    approval_ref: str | None = None


@dataclass(frozen=True)
class Receipt:
    mission_id: str
    operation_id: str
    state: str
    external: bool
    result: Any = None
    provider_receipt_id: str | None = None
    replayed: bool = False
    error: str | None = None


@dataclass(frozen=True)
class Step:
    action: Action
    effect: Callable[[Action], Any]
    verify: Callable[[Any], bool] | None = None
    authorization: Callable[[Action], bool] | None = None


def _intent(action: Action) -> tuple[str, str]:
    if not all(isinstance(v, str) and v.strip()
               for v in (action.mission_id, action.operation_id, action.kind)):
        raise ExecutionDenied("mission, operation and kind must be nonempty")
    if type(action.external) is not bool:
        raise ExecutionDenied("external must be a boolean")
    if not isinstance(action.payload, Mapping):
        raise ExecutionDenied("action payload must be an object")
    try:
        identity = json.dumps({
            "mission_id": action.mission_id,
            "operation_id": action.operation_id,
            "kind": action.kind,
            "payload": dict(action.payload),
            "external": action.external,
            "approval_ref": action.approval_ref,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (ValueError, TypeError) as exc:
        raise ExecutionDenied("action payload is not JSON-serializable") from exc
    key = json.dumps([action.mission_id, action.operation_id], ensure_ascii=False)
    return key, sha256(identity.encode("utf-8")).hexdigest()


class DirectExecutor:
    """Execute what is authorized. No global boot gate, mission-complete gate, or ranker."""

    def __init__(self, journal: str | Path):
        self.journal = Path(journal)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    identity TEXT PRIMARY KEY,
                    intent_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    receipt_json TEXT,
                    external INTEGER NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.journal, timeout=30)

    def _reserve(self, action: Action) -> Receipt | None:
        identity, digest = _intent(action)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT intent_sha256, state, receipt_json FROM actions WHERE identity=?",
                (identity,),
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ExecutionDenied("existing operation identity changed its payload")
                if previous[1] not in {"VERIFIED", "EXECUTED"}:
                    raise ReconciliationRequired("operation previously reserved; reconcile before replay")
                if not previous[2]:
                    raise ReconciliationRequired("completed operation lacks durable receipt")
                return replace(Receipt(**json.loads(previous[2])), replayed=True)
            db.execute(
                "INSERT INTO actions (identity,intent_sha256,state,receipt_json,external)"
                " VALUES (?,?,'RESERVED',NULL,?)",
                (identity, digest, int(action.external)),
            )
        return None

    def _record(self, receipt: Receipt) -> None:
        identity = json.dumps([receipt.mission_id, receipt.operation_id], ensure_ascii=False)
        try:
            serialized = json.dumps(asdict(receipt), ensure_ascii=False, sort_keys=True)
        except (ValueError, TypeError) as exc:
            raise ReconciliationRequired("effect result not persistable; reconcile the reservation") from exc
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM actions WHERE identity=?", (identity,)).fetchone()
            if not row or row[0] != "RESERVED":
                raise ReconciliationRequired("reservation no longer owns the effect")
            db.execute("UPDATE actions SET state=?, receipt_json=? WHERE identity=?",
                       (receipt.state, serialized, identity))

    def run(
        self,
        action: Action,
        effect: Callable[[Action], Any],
        *,
        verify: Callable[[Any], bool] | None = None,
        authorization: Callable[[Action], bool] | None = None,
    ) -> Receipt:
        """Execute directly; an external action needs its own scoped authorization."""
        if not callable(effect):
            raise ExecutionDenied("executable effect callback missing")
        _intent(action)
        if action.external:
            if not isinstance(action.approval_ref, str) or not action.approval_ref.strip():
                raise ExecutionDenied("external effect requires attributable approval")
            if not callable(authorization) or authorization(action) is not True:
                raise ExecutionDenied("external effect lacks actual authorization")
            if not callable(verify):
                raise ExecutionDenied("external effect requires provider readback")
        replay = self._reserve(action)
        if replay is not None:
            if callable(verify) and verify(replay.result) is not True:
                raise ReconciliationRequired("previous receipt failed fresh readback")
            return replay
        try:
            result = effect(action)
            provider_id = None
            if action.external:
                if not isinstance(result, Mapping):
                    raise ReconciliationRequired("provider effect returned no native receipt")
                provider_id = result.get("provider_receipt_id")
                if not isinstance(provider_id, str) or ":" not in provider_id:
                    raise ReconciliationRequired("provider native receipt ID missing")
            verified = callable(verify) and verify(result) is True
            if action.external and not verified:
                raise ReconciliationRequired("provider effect not confirmed by readback")
            receipt = Receipt(
                action.mission_id, action.operation_id,
                "VERIFIED" if verified else "EXECUTED",
                action.external, result, provider_id,
            )
            self._record(receipt)
            return receipt
        except Exception as exc:
            # The effect may already have happened. Keep the reservation, and
            # continue independent work rather than retrying blindly.
            try:
                self._record(Receipt(
                    action.mission_id, action.operation_id, "RECONCILE", action.external,
                    error=f"{type(exc).__name__}: {exc}",
                ))
            except ReconciliationRequired:
                pass
            raise ReconciliationRequired(
                f"{action.operation_id}: effect/readback uncertain; reconcile before retry"
            ) from exc

    def run_many(self, steps: Sequence[Step]) -> list[Receipt]:
        outcomes: list[Receipt] = []
        for step in steps:
            try:
                outcomes.append(self.run(
                    step.action, step.effect, verify=step.verify,
                    authorization=step.authorization,
                ))
            except ExecutionDenied as exc:
                outcomes.append(Receipt(
                    step.action.mission_id, step.action.operation_id,
                    "BLOCKED", step.action.external, error=str(exc),
                ))
            except ReconciliationRequired as exc:
                outcomes.append(Receipt(
                    step.action.mission_id, step.action.operation_id,
                    "RECONCILE", step.action.external, error=str(exc),
                ))
        return outcomes


def _casebook_content(action: Action) -> bytes:
    payload = action.payload
    title = payload.get("title")
    claimant = payload.get("claimant")
    records = payload.get("records")
    if not isinstance(title, str) or not title.strip() or not isinstance(claimant, str) or not claimant.strip():
        raise ExecutionDenied("casebook title and claimant required")
    if not isinstance(records, list) or not records:
        raise ExecutionDenied("casebook requires source-bearing records")
    lines = [f"# {title}", "", f"Claimant: {claimant}", f"Mission: {action.mission_id}",
             "", "## Source records", ""]
    for record in records:
        if not isinstance(record, Mapping):
            raise ExecutionDenied("source record must be an object")
        ref = record.get("source_ref")
        statement = record.get("statement")
        classification = record.get("classification")
        if any(not isinstance(item, str) or not item.strip()
               for item in (ref, statement, classification)):
            raise ExecutionDenied("record requires source_ref, statement and classification")
        lines.append(f"- [{classification}] {statement} — source: {ref}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _casebook_effect(output_dir: Path) -> Callable[[Action], dict[str, Any]]:
    def write(action: Action) -> dict[str, Any]:
        if action.kind != "casebook":
            raise ExecutionDenied("this CLI supports only internal casebook operations")
        if action.external:
            raise ExecutionDenied("CLI has no external provider callback")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", action.operation_id):
            raise ExecutionDenied("operation_id cannot be used as an artifact filename")
        content = _casebook_content(action)
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = output_dir / (action.operation_id + ".md")
        if not artifact.exists():
            with tempfile.NamedTemporaryFile(mode="wb", dir=output_dir, delete=False) as temp:
                tmp_path = Path(temp.name)
                temp.write(content)
                temp.flush()
                os.fsync(temp.fileno())
            try:
                try:
                    os.link(tmp_path, artifact)  # atomic create-if-absent; no overwrite
                except FileExistsError:
                    pass
            finally:
                tmp_path.unlink(missing_ok=True)
        if artifact.read_bytes() != content:
            raise ExecutionDenied("existing artifact differs; original was not overwritten")
        return {
            "artifact_ref": f"file:{artifact.resolve()}",
            "sha256": sha256(content).hexdigest(),
            "bytes": len(content),
        }
    return write


def _verify_casebook(result: Any) -> bool:
    if not isinstance(result, Mapping):
        return False
    ref = result.get("artifact_ref")
    if not isinstance(ref, str) or not ref.startswith("file:"):
        return False
    path = Path(ref[5:])
    return path.is_file() and sha256(path.read_bytes()).hexdigest() == result.get("sha256")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute internal casework immediately without host boot gates")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--journal", required=True)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        mission_id = manifest["mission_id"]
        raw_actions = manifest["actions"]
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ExecutionDenied("manifest actions must be a nonempty array")
        effect = _casebook_effect(Path(args.out_dir))
        steps = [
            Step(Action(
                mission_id=mission_id,
                operation_id=raw["operation_id"],
                kind=raw["kind"],
                payload=raw,
                external=raw.get("external", False),
                approval_ref=raw.get("approval_ref"),
            ), effect, _verify_casebook)
            for raw in raw_actions
        ]
        outcomes = DirectExecutor(args.journal).run_many(steps)
        print(json.dumps({
            "mission_id": mission_id,
            "results": [asdict(r) for r in outcomes],
        }, ensure_ascii=False, sort_keys=True))
        return 0 if all(row.state == "VERIFIED" for row in outcomes) else 1
    except (KeyError, TypeError, ValueError, OSError, ExecutionDenied) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
