"""Direct execution path for Operator-authorized work.

Internal work executes without boot, completeness, or provider-admission gates.
Only an actual external effect requires an authority callback and native readback.
SQLite makes reservations durable; a possible side effect is never blindly replayed.
"""
from __future__ import annotations

import argparse
import ast
import heapq
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
    preflight: Callable[[Action], None] | None = None
    recover: Callable[[Action], Any] | None = None


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

    def recover_internal(
        self,
        action: Action,
        readback: Callable[[Action], Any],
        *,
        verify: Callable[[Any], bool],
    ) -> Receipt:
        """Recover a local immutable effect from readback; never redispatch it."""
        identity, digest = _intent(action)
        if action.external:
            raise ExecutionDenied("internal recovery cannot reconcile external effects")
        if not callable(readback) or not callable(verify):
            raise ExecutionDenied("internal recovery requires readback and verification")
        with self._connect() as db:
            row = db.execute(
                "SELECT intent_sha256,state,external FROM actions WHERE identity=?",
                (identity,),
            ).fetchone()
        if row is None or row[0] != digest or row[2] != 0:
            raise ExecutionDenied("recovery requires the original internal reservation")
        try:
            result = readback(action)
            if result is None or verify(result) is not True:
                raise ReconciliationRequired("no verified artifact to recover")
            receipt = Receipt(action.mission_id, action.operation_id, "VERIFIED", False,
                              result, replayed=True)
            serialized = json.dumps(asdict(receipt), ensure_ascii=False, sort_keys=True,
                                    allow_nan=False)
        except Exception as exc:
            raise ReconciliationRequired("artifact recovery could not prove the effect") from exc
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                "UPDATE actions SET state='VERIFIED',receipt_json=? "
                "WHERE identity=? AND intent_sha256=? AND external=0 "
                "AND state IN ('RESERVED','RECONCILE')",
                (serialized, identity, digest),
            ).rowcount
            if updated != 1:
                raise ReconciliationRequired("reservation changed during recovery")
        return receipt

    def run(
        self,
        action: Action,
        effect: Callable[[Action], Any],
        *,
        verify: Callable[[Any], bool] | None = None,
        authorization: Callable[[Action], bool] | None = None,
        preflight: Callable[[Action], None] | None = None,
        recover: Callable[[Action], Any] | None = None,
    ) -> Receipt:
        """Execute directly; an external action needs its own scoped authorization."""
        if not callable(effect):
            raise ExecutionDenied("executable effect callback missing")
        _intent(action)
        # Pure validation happens before the durable reservation: malformed
        # internal source data must not poison an operation identity.
        if callable(preflight):
            preflight(action)
        if action.external:
            if not isinstance(action.approval_ref, str) or not action.approval_ref.strip():
                raise ExecutionDenied("external effect requires attributable approval")
            if not callable(authorization) or authorization(action) is not True:
                raise ExecutionDenied("external effect lacks actual authorization")
            if not callable(verify):
                raise ExecutionDenied("external effect requires provider readback")
        try:
            replay = self._reserve(action)
        except ReconciliationRequired:
            if not action.external and callable(recover) and callable(verify):
                return self.recover_internal(action, recover, verify=verify)
            raise
        if replay is not None:
            if callable(verify):
                try:
                    if verify(replay.result) is not True:
                        raise ReconciliationRequired("previous receipt failed fresh readback")
                except Exception as exc:
                    raise ReconciliationRequired("previous receipt readback unavailable; reconcile") from exc
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
                    authorization=step.authorization, preflight=step.preflight,
                    recover=step.recover,
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


def _casebook_preflight(action: Action) -> None:
    if action.kind != "casebook" or action.external:
        raise ExecutionDenied("CLI executes only internal casebook operations")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", action.operation_id):
        raise ExecutionDenied("operation_id cannot be used as an artifact filename")
    _casebook_content(action)


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


# Local source context is deliberately explicit: no recursive collection of
# unrelated files, no provider calls, and no source-code execution.
_SOURCE_FILE_LIMIT = 4 * 1024 * 1024
_SOURCE_BUNDLE_LIMIT = 16 * 1024 * 1024


def _source_specs(action: Action) -> tuple[Path, dict[str, str]]:
    if action.external or action.kind != "source_bundle":
        raise ExecutionDenied("source bundles are local operations")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", action.operation_id):
        raise ExecutionDenied("invalid source bundle operation ID")
    root = action.payload.get("source_root")
    files = action.payload.get("files")
    if not isinstance(root, str) or not Path(root).is_absolute():
        raise ExecutionDenied("source_root must be an explicit absolute directory")
    if not isinstance(files, list) or not files:
        raise ExecutionDenied("source bundle requires explicit files and SHA-256 hashes")
    specs = {}
    for entry in files:
        if not isinstance(entry, Mapping):
            raise ExecutionDenied("invalid source file entry")
        name, digest = entry.get("path"), entry.get("sha256")
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                or any(part in {"", ".", ".."} for part in name.split("/"))):
            raise ExecutionDenied("source path must be normalized and relative")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ExecutionDenied("source file requires an exact SHA-256")
        if name in specs:
            raise ExecutionDenied("duplicate source file")
        specs[name] = digest
    return Path(root), dict(sorted(specs.items()))


def _source_bytes(root: Path, name: str) -> bytes:
    root = root.resolve(strict=True)
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ExecutionDenied("source file is outside the authorized root or not a file")
    with path.open("rb") as handle:
        data = handle.read(_SOURCE_FILE_LIMIT + 1)
    if len(data) > _SOURCE_FILE_LIMIT:
        raise ExecutionDenied("source file exceeds bundle limit")
    return data


def build_source_bundle_action(mission_id: str, operation_id: str, source_root: str | Path,
                               paths: Sequence[str]) -> Action:
    """Pin explicitly selected UTF-8 source files before scheduling a bundle."""
    root = Path(source_root).resolve(strict=True)
    if isinstance(paths, str):
        raise ExecutionDenied("paths must be a sequence of relative filenames")
    files = [{"path": name, "sha256": "0" * 64} for name in paths]
    action = Action(mission_id, operation_id, "source_bundle",
                    {"source_root": str(root), "files": files})
    _, specs = _source_specs(action)
    pinned = []
    total = 0
    for name in specs:
        data = _source_bytes(root, name)
        data.decode("utf-8")
        total += len(data)
        if total > _SOURCE_BUNDLE_LIMIT:
            raise ExecutionDenied("source bundle exceeds total byte limit")
        pinned.append({"path": name, "sha256": sha256(data).hexdigest()})
    return replace(action, payload={"source_root": str(root), "files": pinned})


def _bundle_document(action: Action, files: list[dict[str, Any]]) -> bytes:
    return (json.dumps({"schema": "glaciereq.source-bundle.v1",
                        "mission_id": action.mission_id, "operation_id": action.operation_id,
                        "source_root": action.payload["source_root"], "files": files},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def source_bundle_step(action: Action, output_dir: str | Path) -> Step:
    """Create and independently recover a source-bearing, hash-bound context artifact."""
    root, specs = _source_specs(action)
    artifact = Path(output_dir).resolve() / (action.operation_id + ".sources.json")

    def readback(candidate: Action) -> dict[str, Any] | None:
        # Recovery uses the pinned source hashes, not the current source files.
        # This also works after the original source directory is unavailable.
        if candidate != action or artifact.is_symlink() or not artifact.is_file():
            return None
        with artifact.open("rb") as handle:
            content = handle.read(6 * _SOURCE_BUNDLE_LIMIT + 1024 * 1024 + 1)
        if len(content) > 6 * _SOURCE_BUNDLE_LIMIT + 1024 * 1024:
            return None
        doc = json.loads(content)
        files = doc.get("files")
        if not isinstance(files, list) or len(files) != len(specs):
            return None
        expected = []
        total = 0
        for (name, digest), row in zip(specs.items(), files):
            if not isinstance(row, Mapping) or not isinstance(row.get("content"), str):
                return None
            data = row["content"].encode("utf-8")
            if len(data) > _SOURCE_FILE_LIMIT or sha256(data).hexdigest() != digest:
                return None
            total += len(data)
            if total > _SOURCE_BUNDLE_LIMIT:
                return None
            expected.append({"path": name, "sha256": digest, "bytes": len(data),
                             "content": row["content"]})
        if content != _bundle_document(action, expected):
            return None
        return {"artifact_ref": f"file:{artifact}", "sha256": sha256(content).hexdigest(),
                "bytes": len(content), "files": len(expected)}

    def verify(result: Any) -> bool:
        return result is not None and result == readback(action)

    def execute(candidate: Action) -> dict[str, Any]:
        if candidate != action:
            raise ExecutionDenied("source bundle action changed")
        rows = []
        total = 0
        for name, digest in specs.items():
            data = _source_bytes(root, name)
            if sha256(data).hexdigest() != digest:
                raise ExecutionDenied(f"source changed since pinning: {name}")
            total += len(data)
            if total > _SOURCE_BUNDLE_LIMIT:
                raise ExecutionDenied("source bundle exceeds total byte limit")
            rows.append({"path": name, "sha256": digest, "bytes": len(data),
                         "content": data.decode("utf-8")})
        content = _bundle_document(action, rows)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if not artifact.exists():
            with tempfile.NamedTemporaryFile(mode="wb", dir=artifact.parent, delete=False) as temp:
                tmp = Path(temp.name)
                temp.write(content)
                temp.flush()
                os.fsync(temp.fileno())
            try:
                try:
                    os.link(tmp, artifact)
                except FileExistsError:
                    pass
            finally:
                tmp.unlink(missing_ok=True)
        result = readback(action)
        if result is None or result["sha256"] != sha256(content).hexdigest():
            raise ReconciliationRequired("existing source bundle differs; original preserved")
        return result

    return Step(action, execute, verify, recover=readback)


# Evidence retrieval capabilities operate on verified source, never on imported
# or executed source code. Routing is deterministic, not an LLM reasoning claim.
_CONTEXT_STOP = frozenset("a an and are as at be by can does for from how in is it of on or that the to what when where which who why with".split())


def _context_terms(value: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[A-Za-z_][A-Za-z_0-9]*", value)
            if word.casefold() not in _CONTEXT_STOP}


def _evidence(row: Mapping[str, Any], start: int, end: int, kind: str,
              terms: Sequence[str], *, lines: Sequence[str] | None = None,
              **details: Any) -> dict[str, Any]:
    source_lines = row["content"].splitlines() if lines is None else lines
    excerpt = "\n".join(source_lines[start - 1:end])
    return {"path": row["path"], "source_sha256": row["sha256"],
            "start_line": start, "end_line": end, "kind": kind,
            "matched_terms": sorted(terms), "excerpt": excerpt[:4096],
            "excerpt_truncated": len(excerpt) > 4096, **details}


def _python_sources(rows: Sequence[Mapping[str, Any]]):
    for row in rows:
        if row["path"].endswith(".py"):
            try:
                tree = ast.parse(row["content"], filename=row["path"])
            except (SyntaxError, ValueError, RecursionError):
                continue
            yield row, tree, row["content"].splitlines()


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _enclosing_function(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> ast.AST | None:
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def python_symbol_evidence(rows: Sequence[Mapping[str, Any]], objective: str) -> list[dict[str, Any]]:
    """Find named Python definitions, call sites and callback arguments without running code."""
    terms = _context_terms(objective)
    parsed = list(_python_sources(rows))
    definitions = []
    names = set()
    for row, tree, lines in parsed:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.casefold() in terms:
                    names.add(node.name)
                    definitions.append(_evidence(
                        row, node.lineno, min(node.end_lineno or node.lineno, node.lineno + 11),
                        "definition", [node.name.casefold()], lines=lines, symbol=node.name,
                        definition_end_line=node.end_lineno or node.lineno))
    calls = []
    for row, tree, lines in parsed:
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            parent = _enclosing_function(node, parents)
            caller = parent.name if parent is not None else None
            if name in names:
                calls.append(_evidence(row, node.lineno, min(node.end_lineno or node.lineno,
                                                           node.lineno + 7),
                                       "syntactic_call_candidate", [name.casefold()], lines=lines,
                                       symbol=name, caller=caller))
            for argument in [*node.args, *(kw.value for kw in node.keywords)]:
                name = _call_name(argument)
                if name in names:
                    calls.append(_evidence(row, argument.lineno, argument.end_lineno or argument.lineno,
                                           "callback_argument_candidate", [name.casefold()], lines=lines,
                                           symbol=name, caller=caller, passed_to=_call_name(node.func)))
    key = lambda hit: (hit["path"], hit["start_line"], hit["symbol"], hit["kind"])
    return sorted(definitions, key=key) + sorted(calls, key=key)


def python_dependency_trace(rows: Sequence[Mapping[str, Any]],
                            selected: Sequence[Mapping[str, Any]], *, limit: int) -> dict[str, Any]:
    """Apply retrieved definitions to a local static dependency analysis.

    Same-file symbol references are candidates, not a runtime-resolved call graph.
    """
    roots = {(hit["path"], hit["start_line"]) for hit in selected if hit["kind"] == "definition"}
    edges = []
    targets = set()
    total_edges = 0
    for row, tree, lines in _python_sources(rows):
        defs = [node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        by_name = {}
        for node in defs:
            by_name.setdefault(node.name, []).append(node)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for root in defs:
            if (row["path"], root.lineno) not in roots:
                continue
            for node in ast.walk(root):
                if not isinstance(node, ast.Call):
                    continue
                # Class construction does not imply execution of every method.
                owner = _enclosing_function(node, parents)
                if isinstance(root, ast.ClassDef):
                    if owner is not None and (owner.name != "__init__" or parents.get(owner) is not root):
                        continue
                elif owner is not root:
                    continue
                references = [(_call_name(node.func), "dependency_call")]
                references.extend((_call_name(arg), "dependency_callback_argument")
                                  for arg in [*node.args, *(kw.value for kw in node.keywords)])
                for target, kind in sorted(set(references), key=lambda item: (item[0] or "", item[1])):
                    candidates = by_name.get(target, [])
                    if not candidates:
                        continue
                    targets.add(target)
                    total_edges += 1
                    if len(edges) >= limit:
                        continue
                    edges.append({"from_symbol": root.name, "to_symbol": target,
                                  "resolution": "same_file_name_candidate",
                                  "call_site": _evidence(row, node.lineno,
                                      min(node.end_lineno or node.lineno, node.lineno + 7),
                                      kind, [target.casefold()], lines=lines),
                                  "candidate_definition_count": len(candidates),
                                  "candidate_definitions": [
                                      _evidence(row, item.lineno,
                                          min(item.end_lineno or item.lineno, item.lineno + 11),
                                          "dependency_definition", [target.casefold()], lines=lines,
                                          symbol=item.name) for item in candidates[:limit]]})
    edges.sort(key=lambda edge: (edge["call_site"]["path"], edge["call_site"]["start_line"],
                                 edge["from_symbol"], edge["to_symbol"]))
    callbacks = [hit for hit in selected if hit["kind"] == "callback_argument_candidate"]
    return {"capability": "python_dependency_trace", "resolution": "static_candidates_only",
            "root_definitions": len(roots), "total_edges": total_edges,
            "dependency_targets": sorted(targets),
            "edges": edges, "callback_arguments": callbacks[:limit],
            "truncated": total_edges > limit or len(callbacks) > limit}


def text_context_evidence(rows: Sequence[Mapping[str, Any]], objective: str, *, limit: int,
                          exclude: Sequence[Mapping[str, Any]] = ()) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    """Rank exact token matches with bounded result memory and full match counts."""
    terms = _context_terms(objective)
    total = 0
    counts = dict.fromkeys(sorted(terms), 0)
    covered = {(hit["path"], line) for hit in exclude
               for line in range(hit["start_line"], hit["end_line"] + 1)}

    def candidates():
        nonlocal total
        for row in rows:
            lines = row["content"].splitlines()
            for index, line in enumerate(lines):
                matched = terms & _context_terms(line)
                for term in matched:
                    counts[term] += 1
                if matched and (row["path"], index + 1) not in covered:
                    total += 1
                    yield _evidence(row, index + 1, index + 1, "text_match", matched, lines=lines)

    hits = heapq.nsmallest(max(1, limit), candidates(),
                          key=lambda hit: (-len(hit["matched_terms"]), hit["path"], hit["start_line"]))
    return hits[:limit], total, counts


def resolve_source_context(rows: Sequence[Mapping[str, Any]], objective: str,
                           *, limit: int = 40) -> dict[str, Any]:
    """Select retrieval, execute it, and apply its result to downstream analysis."""
    if not isinstance(objective, str) or len(objective) > 4096 or not _context_terms(objective):
        raise ExecutionDenied("context objective requires meaningful source terms")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ExecutionDenied("context hit limit must be between 1 and 500")
    structural = python_symbol_evidence(rows, objective)
    textual, text_count, coverage = text_context_evidence(
        rows, objective, limit=max(0, limit - len(structural)), exclude=structural)
    hits = structural + textual
    total = len(structural) + text_count
    if structural:
        capability = "python_symbol_evidence"
        analysis = python_dependency_trace(rows, structural, limit=limit)
    else:
        capability = "text_context_evidence"
        analysis = {"capability": "term_coverage", "line_match_counts": coverage,
                    "unmatched_terms": [term for term, count in coverage.items() if not count]}
    return {"objective": objective, "capability": capability,
            "available_capabilities": ["python_symbol_evidence", "text_context_evidence",
                                       "python_dependency_trace", "term_coverage"],
            "answer_status": "matches" if total else "no_matches",
            "source_files": len(rows), "total_hits": total, "truncated": total > limit,
            "hits": hits[:limit], "analysis": analysis,
            "definition_names": sorted({hit["symbol"] for hit in structural
                                        if hit["kind"] == "definition"})}


def source_context_step(action: Action, output_dir: str | Path) -> Step:
    """Consume an exact source bundle and produce independently recoverable evidence."""
    if action.external or action.kind != "source_context":
        raise ExecutionDenied("source context is a local operation")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", action.operation_id):
        raise ExecutionDenied("invalid source context operation ID")
    source = Action(action.mission_id, action.payload["source_operation_id"], "source_bundle",
                    {"source_root": action.payload["source_root"], "files": action.payload["files"]})
    if source.operation_id == action.operation_id:
        raise ExecutionDenied("source and context operations must have distinct identities")
    bundle = source_bundle_step(source, output_dir)
    objective = action.payload.get("objective")
    limit = action.payload.get("limit", 40)
    if not isinstance(objective, str) or len(objective) > 4096 or not _context_terms(objective):
        raise ExecutionDenied("context objective requires meaningful source terms")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ExecutionDenied("context hit limit must be between 1 and 500")
    artifact = Path(output_dir).resolve() / (action.operation_id + ".context.json")

    def document() -> bytes:
        try:
            receipt = bundle.recover(source)
            if receipt is None:
                raise ExecutionDenied("verified source bundle is not available")
            path = Path(receipt["artifact_ref"][5:])
            with path.open("rb") as handle:
                content = handle.read(receipt["bytes"] + 1)
            if sha256(content).hexdigest() != receipt["sha256"]:
                raise ExecutionDenied("source bundle changed during retrieval")
            rows = json.loads(content)["files"]
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ExecutionDenied("source bundle is unreadable or invalid") from exc
        result = resolve_source_context(rows, objective, limit=limit)
        result.update(schema="glaciereq.source-context.v1", mission_id=action.mission_id,
                      operation_id=action.operation_id, source_bundle_sha256=receipt["sha256"])
        return (json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n").encode("utf-8")

    def preflight(candidate: Action) -> None:
        if candidate != action:
            raise ExecutionDenied("context operation changed")
        document()

    def recover(candidate: Action) -> dict[str, Any] | None:
        if candidate != action or artifact.is_symlink() or not artifact.is_file():
            return None
        expected = document()
        with artifact.open("rb") as handle:
            actual = handle.read(len(expected) + 1)
        if actual != expected:
            return None
        result = json.loads(actual)
        return {"artifact_ref": f"file:{artifact}", "sha256": sha256(actual).hexdigest(),
                "bytes": len(actual), "capability": result["capability"],
                "answer_status": result["answer_status"], "hits": len(result["hits"])}

    def verify(result: Any) -> bool:
        return result is not None and result == recover(action)

    def execute(candidate: Action) -> dict[str, Any]:
        if candidate != action:
            raise ExecutionDenied("context operation changed")
        content = document()
        artifact.parent.mkdir(parents=True, exist_ok=True)
        if not artifact.exists():
            with tempfile.NamedTemporaryFile(mode="wb", dir=artifact.parent, delete=False) as temp:
                tmp = Path(temp.name)
                temp.write(content)
                temp.flush()
                os.fsync(temp.fileno())
            try:
                try:
                    os.link(tmp, artifact)
                except FileExistsError:
                    pass
            finally:
                tmp.unlink(missing_ok=True)
        result = recover(action)
        if result is None:
            raise ReconciliationRequired("context artifact conflicts; original preserved")
        return result

    return Step(action, execute, verify, preflight=preflight, recover=recover)


def prepare_context_mission(manifest_path: str | Path, *, mission_id: str, operation_id: str,
                            objective: str, source_root: str | Path, paths: Sequence[str],
                            limit: int = 40, follow_dependencies: bool = True) -> Action:
    """Pin a new agent objective once, or recover its immutable existing manifest."""
    if not isinstance(objective, str) or len(objective) > 4096 or not _context_terms(objective):
        raise ExecutionDenied("context objective requires meaningful source terms")
    if type(limit) is not int or not 1 <= limit <= 500 or type(follow_dependencies) is not bool:
        raise ExecutionDenied("invalid context retrieval options")
    if isinstance(paths, (str, bytes)):
        raise ExecutionDenied("paths must be a sequence of relative filenames")
    root = Path(source_root).resolve()
    requested = Action(mission_id, operation_id, "source_bundle", {
        "source_root": str(root), "files": [{"path": name, "sha256": "0" * 64} for name in paths]})
    _intent(requested)
    _, requested_specs = _source_specs(requested)
    manifest = Path(manifest_path)

    def load() -> Action:
        if manifest.is_symlink() or not manifest.is_file():
            raise ExecutionDenied("manifest must be a regular file")
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        actions = doc.get("actions")
        if doc.get("mission_id") != mission_id or not isinstance(actions, list) or len(actions) != 1:
            raise ExecutionDenied("existing manifest belongs to different work")
        payload = actions[0]
        if (payload.get("kind") != "context_mission" or payload.get("operation_id") != operation_id
                or payload.get("objective") != objective or payload.get("source_root") != str(root)
                or payload.get("limit") != limit or payload.get("follow_dependencies") is not follow_dependencies
                or payload.get("external", False) is not False):
            raise ExecutionDenied("existing manifest intent differs; original preserved")
        action = Action(mission_id, operation_id, "context_mission", payload)
        _, pinned = _source_specs(replace(action, kind="source_bundle"))
        if set(pinned) != set(requested_specs):
            raise ExecutionDenied("existing manifest source scope differs; original preserved")
        return action

    if manifest.exists() or manifest.is_symlink():
        return load()
    pinned = build_source_bundle_action(mission_id, operation_id, root, paths)
    payload = {**pinned.payload, "operation_id": operation_id, "kind": "context_mission",
               "objective": objective, "limit": limit, "follow_dependencies": follow_dependencies}
    content = (json.dumps({"mission_id": mission_id, "actions": [payload]}, ensure_ascii=False,
                          sort_keys=True, indent=2) + "\n").encode("utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="wb", dir=manifest.parent, delete=False) as temp:
        tmp = Path(temp.name)
        temp.write(content)
        temp.flush()
        os.fsync(temp.fileno())
    try:
        try:
            os.link(tmp, manifest)
        except FileExistsError:
            pass
    finally:
        tmp.unlink(missing_ok=True)
    return load()


def prepare_context_followup(previous_manifest: str | Path, manifest_path: str | Path, *,
                             mission_id: str, operation_id: str, objective: str,
                             limit: int = 40, follow_dependencies: bool = True) -> Action:
    """Create another objective over the same pinned source without rescanning live files."""
    if not isinstance(objective, str) or len(objective) > 4096 or not _context_terms(objective):
        raise ExecutionDenied("context objective requires meaningful source terms")
    if type(limit) is not int or not 1 <= limit <= 500 or type(follow_dependencies) is not bool:
        raise ExecutionDenied("invalid context retrieval options")
    prior_path = Path(previous_manifest)
    if prior_path.is_symlink() or not prior_path.is_file():
        raise ExecutionDenied("previous manifest must be a regular file")
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    actions = prior.get("actions")
    if prior.get("mission_id") != mission_id or not isinstance(actions, list) or len(actions) != 1:
        raise ExecutionDenied("follow-up requires one prior manifest in the same mission")
    raw = actions[0]
    if raw.get("kind") != "context_mission" or raw.get("external", False) is not False:
        raise ExecutionDenied("follow-up requires an internal context mission")
    pinned = Action(mission_id, operation_id, "source_bundle",
                    {"source_root": raw["source_root"], "files": raw["files"]})
    _intent(pinned)
    root, specs = _source_specs(pinned)
    payload = {"source_root": str(root), "files": [
        {"path": name, "sha256": digest} for name, digest in specs.items()],
        "operation_id": operation_id, "kind": "context_mission", "objective": objective,
        "limit": limit, "follow_dependencies": follow_dependencies}
    doc = {"mission_id": mission_id, "actions": [payload]}
    content = (json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    manifest = Path(manifest_path)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if not manifest.exists() and not manifest.is_symlink():
        with tempfile.NamedTemporaryFile(mode="wb", dir=manifest.parent, delete=False) as temp:
            tmp = Path(temp.name)
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
        try:
            try:
                os.link(tmp, manifest)
            except FileExistsError:
                pass
        finally:
            tmp.unlink(missing_ok=True)
    if manifest.is_symlink() or not manifest.is_file():
        raise ExecutionDenied("follow-up manifest must be a regular file")
    if json.loads(manifest.read_text(encoding="utf-8")) != doc:
        raise ExecutionDenied("existing follow-up manifest intent differs; original preserved")
    return Action(mission_id, operation_id, "context_mission", payload)


def context_mission_steps(action: Action, output_dir: str | Path) -> list[Step]:
    """Expand one source objective into acquisition and retrieval; reuse exact snapshots."""
    if action.external or action.kind != "context_mission":
        raise ExecutionDenied("context missions are local operations")
    raw_source = Action(action.mission_id, "source", "source_bundle",
                        {"source_root": action.payload["source_root"], "files": action.payload["files"]})
    root, specs = _source_specs(raw_source)
    payload = {"source_root": str(root), "files": [
        {"path": name, "sha256": digest} for name, digest in specs.items()]}
    identity = json.dumps([action.mission_id, payload], sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"))
    source_id = "source-" + sha256(identity.encode("utf-8")).hexdigest()
    source = replace(raw_source, operation_id=source_id, payload=payload)
    context = Action(action.mission_id, action.operation_id, "source_context",
                     {**source.payload, "source_operation_id": source_id,
                      "objective": action.payload.get("objective"),
                      "limit": action.payload.get("limit", 40)})
    return [source_bundle_step(source, output_dir), source_context_step(context, output_dir)]


def _verified_context_packet(receipt: Receipt) -> dict[str, Any]:
    if receipt.state != "VERIFIED" or not isinstance(receipt.result, Mapping):
        raise ReconciliationRequired("context operation has no verified receipt")
    try:
        path = Path(receipt.result["artifact_ref"][5:])
        with path.open("rb") as handle:
            content = handle.read(receipt.result["bytes"] + 1)
        if sha256(content).hexdigest() != receipt.result["sha256"]:
            raise ReconciliationRequired("context packet changed before application")
        return json.loads(content)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ReconciliationRequired("verified context packet could not be applied") from exc


def run_context_mission(executor: DirectExecutor, action: Action,
                        output_dir: str | Path) -> dict[str, Any]:
    """Execute a source objective and advance its discovered dependency frontier.

    Each follow-up is selected from verified prior output, uses the same pinned
    snapshot and gets a stable durable operation identity. The frontier is
    finite (the selected source files), not an arbitrary turn count.
    """
    follow = action.payload.get("follow_dependencies", True)
    if type(follow) is not bool:
        raise ExecutionDenied("follow_dependencies must be boolean")
    receipts = executor.run_many(context_mission_steps(action, output_dir))
    if any(receipt.state != "VERIFIED" for receipt in receipts):
        return {"status": "incomplete", "receipts": [asdict(row) for row in receipts],
                "followups": [], "unresolved_dependencies": []}
    context = _verified_context_packet(receipts[-1])
    seen = set(context["definition_names"])
    pending = set(context["analysis"].get("dependency_targets", [])) - seen
    unresolved = set()
    followups = []
    while follow and pending:
        # Keep the actual query within the accepted input size; no symbol is
        # dropped merely because a particular batch is full.
        batch = []
        size = 0
        for name in sorted(pending):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) or len(name) > 4096:
                unresolved.add(name)
                continue
            if size + len(name) + 1 > 4096:
                break
            batch.append(name)
            size += len(name) + 1
        pending.difference_update(unresolved)
        if not batch:
            break
        seen.update(batch)
        pending.difference_update(batch)
        key = json.dumps([action.operation_id, batch], ensure_ascii=False, separators=(",", ":"))
        operation_id = "trace-" + sha256(key.encode("utf-8")).hexdigest()
        next_action = replace(action, operation_id=operation_id,
                              payload={**action.payload, "objective": " ".join(batch),
                                       "follow_dependencies": False})
        next_receipts = executor.run_many(context_mission_steps(next_action, output_dir))
        receipts.extend(next_receipts)
        if any(row.state != "VERIFIED" for row in next_receipts):
            unresolved.update(batch)
            continue
        try:
            packet = _verified_context_packet(next_receipts[-1])
        except ReconciliationRequired:
            unresolved.update(batch)
            continue
        followups.append(packet)
        found = set(packet["definition_names"])
        unresolved.update(set(batch) - found)
        seen.update(found)
        pending.update(set(packet["analysis"].get("dependency_targets", [])) - seen - unresolved)
    return {"status": "incomplete" if unresolved or pending else "verified",
            "receipts": [asdict(row) for row in receipts], "context": context,
            "followups": followups, "unresolved_dependencies": sorted(unresolved),
            "unexpanded_dependencies": sorted(pending), "visited_symbols": sorted(seen)}


def local_mission_step(action: Action, output_dir: str | Path) -> Step:
    """Route supported internal work into the existing durable dispatcher."""
    if action.kind == "source_bundle":
        return source_bundle_step(action, output_dir)
    if action.kind == "source_context":
        return source_context_step(action, output_dir)
    return Step(action, _casebook_effect(Path(output_dir)), _verify_casebook,
                preflight=_casebook_preflight)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute internal casework, source bundles or context missions with durable receipts")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--objective", help="Prepare and execute a source context mission")
    parser.add_argument("--mission-id")
    parser.add_argument("--operation-id")
    parser.add_argument("--source-root")
    parser.add_argument("--source-file", action="append")
    parser.add_argument("--from-manifest", help="Reuse a prior pinned context mission")
    args = parser.parse_args(argv)
    try:
        if args.objective is not None:
            if not all((args.mission_id, args.operation_id)):
                raise ExecutionDenied("objective requires mission ID and operation ID")
            if args.from_manifest:
                if args.source_root or args.source_file:
                    raise ExecutionDenied("choose prior manifest or new source scope, not both")
                prepare_context_followup(args.from_manifest, args.manifest, mission_id=args.mission_id,
                                         operation_id=args.operation_id, objective=args.objective)
            else:
                if not all((args.source_root, args.source_file)):
                    raise ExecutionDenied("new objective requires source root and files")
                prepare_context_mission(args.manifest, mission_id=args.mission_id,
                                        operation_id=args.operation_id, objective=args.objective,
                                        source_root=args.source_root, paths=args.source_file)
        elif any((args.mission_id, args.operation_id, args.source_root, args.source_file, args.from_manifest)):
            raise ExecutionDenied("source preparation options require --objective")
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        mission_id = manifest["mission_id"]
        raw_actions = manifest["actions"]
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ExecutionDenied("manifest actions must be a nonempty array")
        executor = DirectExecutor(args.journal)
        outcomes = []
        contexts = []
        for raw in raw_actions:
            action = Action(mission_id=mission_id, operation_id=raw["operation_id"],
                            kind=raw["kind"], payload=raw, external=raw.get("external", False),
                            approval_ref=raw.get("approval_ref"))
            try:
                if action.kind == "context_mission":
                    result = run_context_mission(executor, action, args.out_dir)
                    outcomes.extend(result["receipts"])
                    contexts.append({"operation_id": action.operation_id, "status": result["status"],
                                     "followups": len(result["followups"]),
                                     "unresolved_dependencies": result["unresolved_dependencies"],
                                     "unexpanded_dependencies": result.get("unexpanded_dependencies", [])})
                else:
                    outcomes.extend(asdict(row) for row in executor.run_many([
                        local_mission_step(action, args.out_dir)]))
            except ExecutionDenied as exc:
                outcomes.append(asdict(Receipt(mission_id, action.operation_id, "BLOCKED",
                                               action.external, error=str(exc))))
            except ReconciliationRequired as exc:
                outcomes.append(asdict(Receipt(mission_id, action.operation_id, "RECONCILE",
                                               action.external, error=str(exc))))
        result = {"mission_id": mission_id, "results": outcomes}
        if contexts:
            result["context_missions"] = contexts
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if (all(row["state"] == "VERIFIED" for row in outcomes)
                     and all(row["status"] == "verified" for row in contexts)) else 1
    except (KeyError, TypeError, ValueError, OSError, ExecutionDenied) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
