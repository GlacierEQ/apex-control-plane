"""Evidence-led audit engine for the APEX control plane.

The engine observes repository and connector state, persists one run-specific receipt,
and immediately reads that receipt back before a run can be considered complete.
Connector probes never authorize external action.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - exercised through dependency-degraded behavior
    requests = None

SCHEMA_VERSION = "1.1.0"


class AuditInvariantError(RuntimeError):
    """Raised when a persisted audit run fails its readback contract."""


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str
    domain: str
    title: str
    evidence: str
    action: str
    evidence_state: str = "OBSERVED"
    evidence_source_class: str = "EVIDENCE"
    action_state: str = "PROPOSED"
    action_source_class: str = "AGENT"
    auto_execute: bool = False
    status: str = "open"
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class ConnectorStatus:
    name: str
    declared: bool = False
    authenticated: bool = False
    reachable: bool = False
    receipt_verified: bool = False
    action_authorized: bool = False
    action_capable: bool = False
    notes: str = ""

    def probe_score(self) -> int:
        return sum((self.declared, self.authenticated, self.reachable))

    def state(self) -> str:
        if self.probe_score() == 3:
            return "REACHABLE_NON_AUTHORIZING"
        if self.probe_score() >= 1:
            return "DEGRADED"
        return "OFFLINE"


@dataclass(slots=True)
class AuditRun:
    run_id: str
    started_at: str
    source_sha: str | None = None
    workflow_run_id: str | None = None
    completed_at: str | None = None
    status: str = "running"
    findings: list[Finding] = field(default_factory=list)
    connectors: list[ConnectorStatus] = field(default_factory=list)
    actions_executed: list[str] = field(default_factory=list)
    p0_count: int = 0
    p1_count: int = 0
    external_action_authorized: bool = False


@dataclass(frozen=True, slots=True)
class AuditReadback:
    run_id: str
    log_path: Path
    queue_path: Path
    proof_path: Path
    log_sha256: str
    queue_sha256: str
    source_sha: str | None
    status: str
    external_action_authorized: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_run_id(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id).strip("._") or "unknown-run"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _response_json_object(response: Any) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def validate_connectors() -> list[ConnectorStatus]:
    """Probe configured providers without granting action authority."""
    statuses: list[ConnectorStatus] = []

    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_repo = os.environ.get("GITHUB_REPO", "GlacierEQ/apex-control-plane")
    github = ConnectorStatus(name="GitHub", declared=True, notes="GITHUB_TOKEN missing")
    if github_token and requests:
        try:
            response = requests.get(
                f"https://api.github.com/repos/{github_repo}",
                headers={"Authorization": f"Bearer {github_token}"},
                timeout=10,
            )
            payload = _response_json_object(response) if response.status_code == 200 else None
            if response.status_code == 200 and payload is not None:
                github = ConnectorStatus(
                    name="GitHub",
                    declared=True,
                    authenticated=True,
                    reachable=True,
                    notes=f"repository={payload.get('full_name', github_repo)}",
                )
            elif response.status_code == 200:
                github = ConnectorStatus(
                    name="GitHub", declared=True, notes="invalid_json_response"
                )
            else:
                github = ConnectorStatus(
                    name="GitHub", declared=True, notes=f"http_status={response.status_code}"
                )
        except requests.RequestException as error:
            github = ConnectorStatus(name="GitHub", declared=True, notes=str(error))
    elif github_token:
        github = ConnectorStatus(
            name="GitHub", declared=True, notes="requests dependency unavailable"
        )
    statuses.append(github)

    notion_token = os.environ.get("NOTION_TOKEN", "")
    notion = ConnectorStatus(name="Notion", declared=True, notes="NOTION_TOKEN missing")
    if notion_token and requests:
        try:
            response = requests.get(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {notion_token}",
                    "Notion-Version": "2022-06-28",
                },
                timeout=10,
            )
            if response.status_code == 200:
                notion = ConnectorStatus(
                    name="Notion", declared=True, authenticated=True, reachable=True
                )
            else:
                notion = ConnectorStatus(
                    name="Notion", declared=True, notes=f"http_status={response.status_code}"
                )
        except requests.RequestException as error:
            notion = ConnectorStatus(name="Notion", declared=True, notes=str(error))
    elif notion_token:
        notion = ConnectorStatus(
            name="Notion", declared=True, notes="requests dependency unavailable"
        )
    statuses.append(notion)

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    supabase = ConnectorStatus(
        name="Supabase", declared=True, notes="SUPABASE_URL or SUPABASE_KEY missing"
    )
    if supabase_url and supabase_key and requests:
        try:
            response = requests.get(
                f"{supabase_url.rstrip('/')}/rest/v1/",
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                supabase = ConnectorStatus(
                    name="Supabase", declared=True, authenticated=True, reachable=True
                )
            else:
                supabase = ConnectorStatus(
                    name="Supabase", declared=True, notes=f"http_status={response.status_code}"
                )
        except requests.RequestException as error:
            supabase = ConnectorStatus(name="Supabase", declared=True, notes=str(error))
    elif supabase_url and supabase_key:
        supabase = ConnectorStatus(
            name="Supabase", declared=True, notes="requests dependency unavailable"
        )
    statuses.append(supabase)

    return statuses


CREDENTIAL_PATTERNS = (
    (
        "GitHub token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("xAI API key", re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b")),
    ("Notion token", re.compile(r"\bntn_[A-Za-z0-9]{20,}\b")),
    ("Legacy Notion token", re.compile(r"\bsecret_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Stripe live key", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    (
        "JWT credential",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"
        ),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "password assignment",
        re.compile(
            r"(?:^|[\s{,\"'])(?:[A-Za-z0-9_]*PASSWORD[A-Za-z0-9_]*|password|\"password\"|'password')"
            r"\s*(?:=|:)\s*(?:[\"'][^\"'\n]{8,}[\"']|[^\s,#}\]\"']{8,})",
            re.IGNORECASE,
        ),
    ),
)

SECRET_SCAN_EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "audit_log",
    "audit_logs",
    "action_queue",
    "findings",
}
SECRET_SCAN_SUFFIXES = {
    ".py",
    ".ts",
    ".js",
    ".go",
    ".env",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".toml",
    ".sh",
    ".pem",
    ".key",
    ".ini",
    ".conf",
}
TOKEN_ASSIGNMENT = re.compile(r"(?m)^\s*GITHUB_TOKEN\s*:\s*(?P<value>.+?)\s*$")
APPROVED_TOKEN_EXPRESSION = re.compile(
    r"\$\{\{\s*(?:secrets\.[A-Za-z_][A-Za-z0-9_]*|github\.token|env\.GITHUB_TOKEN)\s*\}\}"
)


def _is_approved_token_source(value: str) -> bool:
    candidate = value.strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {"'", '"'}:
        candidate = candidate[1:-1].strip()
    return APPROVED_TOKEN_EXPRESSION.fullmatch(candidate) is not None


def should_scan_secret_file(filename: str) -> bool:
    normalized = filename.casefold()
    if normalized == ".env" or normalized.startswith(".env."):
        return True
    return Path(normalized).suffix in SECRET_SCAN_SUFFIXES


def scan_for_secrets(root: str = ".") -> list[Finding]:
    findings: list[Finding] = []
    for file_path in Path(root).rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in SECRET_SCAN_EXCLUDED_DIRS for part in file_path.parts):
            continue
        if not should_scan_secret_file(file_path.name):
            continue
        try:
            text = file_path.read_text(errors="ignore", encoding="utf-8")
        except OSError:
            continue
        for label, pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(
                        severity="P0",
                        domain="security",
                        title=f"Credential-shaped value in {file_path}",
                        evidence=f"{label} pattern matched; value redacted from audit output",
                        action=(
                            f"Remove the credential from {file_path}, rotate it if live, and inject "
                            "it through the approved secret path"
                        ),
                    )
                )
                break
    return findings


def detect_workflow_drift(root: str = ".") -> list[Finding]:
    workflow_dir = Path(root) / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    findings: list[Finding] = []
    for file_path in sorted(workflow_dir.iterdir()):
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(errors="ignore", encoding="utf-8")
        except OSError:
            continue
        for match in TOKEN_ASSIGNMENT.finditer(content):
            value = match.group("value")
            if _is_approved_token_source(value):
                continue
            line_number = content.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    severity="P1",
                    domain="cicd",
                    title=f"Workflow {file_path.name}:{line_number} has an unsafe token source",
                    evidence="GITHUB_TOKEN assignment lacks an approved explicit token source",
                    action="Audit and tighten workflow token sourcing",
                )
            )
    return findings


def analyze_structure(root: str = ".") -> list[Finding]:
    base = Path(root)
    checks = (
        (
            ".env.example",
            "P1",
            "security",
            "Missing .env.example",
            "Create .env.example with variable names only",
        ),
        (
            ".gitignore",
            "P1",
            "security",
            "Missing .gitignore",
            "Create a comprehensive .gitignore",
        ),
        (
            "README.md",
            "P2",
            "documentation",
            "Missing README.md",
            "Create repository documentation",
        ),
    )
    findings: list[Finding] = []
    for relative, severity, domain, title, action in checks:
        if not (base / relative).exists():
            findings.append(
                Finding(
                    severity=severity,
                    domain=domain,
                    title=title,
                    evidence=f"{relative} was not present at audit time",
                    action=action,
                )
            )
    return findings


def _run_paths(run_id: str, root: str | Path = ".") -> tuple[Path, Path, Path]:
    safe = _safe_run_id(run_id)
    base = Path(root)
    return (
        base / "audit_log" / f"run_{safe}.json",
        base / "action_queue" / f"queue_{safe}.json",
        base / "audit_log" / f"proof_{safe}.json",
    )


def persist_run(run: AuditRun, root: str | Path = ".") -> tuple[Path, Path, Path]:
    log_path, queue_path, proof_path = _run_paths(run.run_id, root)
    run_payload = {
        "schema_version": SCHEMA_VERSION,
        "run": asdict(run),
    }
    queue_payload = [
        {
            "severity": finding.severity,
            "domain": finding.domain,
            "title": finding.title,
            "evidence": finding.evidence,
            "evidence_state": finding.evidence_state,
            "evidence_source_class": finding.evidence_source_class,
            "action": finding.action,
            "action_state": finding.action_state,
            "action_source_class": finding.action_source_class,
            "auto_execute": finding.auto_execute,
        }
        for finding in run.findings
        if not finding.resolved
    ]
    _atomic_write_json(log_path, run_payload)
    _atomic_write_json(queue_path, queue_payload)
    proof_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run.run_id,
        "source_sha": run.source_sha,
        "log_path": str(log_path.relative_to(Path(root))),
        "queue_path": str(queue_path.relative_to(Path(root))),
        "log_sha256": _sha256_file(log_path),
        "queue_sha256": _sha256_file(queue_path),
        "external_action_authorized": False,
        "created_at": _iso_z(_utc_now()),
    }
    _atomic_write_json(proof_path, proof_payload)
    return log_path, queue_path, proof_path


def verify_run_receipt(run_id: str, root: str | Path = ".") -> AuditReadback:
    log_path, queue_path, proof_path = _run_paths(run_id, root)
    for path in (log_path, queue_path, proof_path):
        if not path.is_file():
            raise AuditInvariantError(f"required audit receipt missing: {path}")

    log_payload = json.loads(log_path.read_text(encoding="utf-8"))
    queue_payload = json.loads(queue_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    run_payload = log_payload.get("run") if isinstance(log_payload, dict) else None
    if not isinstance(log_payload, dict) or not isinstance(proof, dict):
        raise AuditInvariantError("audit receipt envelopes must be JSON objects")
    if log_payload.get("schema_version") != SCHEMA_VERSION:
        raise AuditInvariantError("audit log schema version mismatch")
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise AuditInvariantError("audit proof schema version mismatch")
    if not isinstance(run_payload, dict):
        raise AuditInvariantError("audit log is missing run object")
    if run_payload.get("run_id") != run_id or proof.get("run_id") != run_id:
        raise AuditInvariantError("audit receipt run_id mismatch")
    if proof.get("source_sha") != run_payload.get("source_sha"):
        raise AuditInvariantError("audit proof source_sha mismatch")
    expected_log_ref = str(log_path.relative_to(Path(root)))
    expected_queue_ref = str(queue_path.relative_to(Path(root)))
    if proof.get("log_path") != expected_log_ref or proof.get("queue_path") != expected_queue_ref:
        raise AuditInvariantError("audit proof path binding mismatch")
    if not isinstance(queue_payload, list) or not all(
        isinstance(item, dict) for item in queue_payload
    ):
        raise AuditInvariantError("audit action queue must be a list of objects")
    if proof.get("log_sha256") != _sha256_file(log_path):
        raise AuditInvariantError("audit log digest mismatch")
    if proof.get("queue_sha256") != _sha256_file(queue_path):
        raise AuditInvariantError("audit queue digest mismatch")
    if run_payload.get("status") not in {"clean", "findings"}:
        raise AuditInvariantError("audit run did not reach a terminal status")
    if not run_payload.get("completed_at"):
        raise AuditInvariantError("audit run is missing completed_at")
    if run_payload.get("external_action_authorized") is not False:
        raise AuditInvariantError("audit run must remain non-authorizing")
    if proof.get("external_action_authorized") is not False:
        raise AuditInvariantError("audit proof must remain non-authorizing")

    return AuditReadback(
        run_id=run_id,
        log_path=log_path,
        queue_path=queue_path,
        proof_path=proof_path,
        log_sha256=proof["log_sha256"],
        queue_sha256=proof["queue_sha256"],
        source_sha=run_payload.get("source_sha"),
        status=run_payload["status"],
        external_action_authorized=False,
    )


def execute_audit(
    *,
    run_id: str,
    root: str | Path = ".",
    source_sha: str | None = None,
    workflow_run_id: str | None = None,
) -> tuple[AuditRun, AuditReadback]:
    started = _utc_now()
    run = AuditRun(
        run_id=run_id,
        started_at=_iso_z(started),
        source_sha=source_sha,
        workflow_run_id=workflow_run_id,
    )
    run.connectors = validate_connectors()
    run.findings.extend(scan_for_secrets(str(root)))
    run.findings.extend(detect_workflow_drift(str(root)))
    run.findings.extend(analyze_structure(str(root)))
    run.p0_count = sum(f.severity == "P0" for f in run.findings)
    run.p1_count = sum(f.severity == "P1" for f in run.findings)
    run.status = "findings" if run.findings else "clean"
    run.completed_at = _iso_z(_utc_now())
    persist_run(run, root)
    readback = verify_run_receipt(run.run_id, root)
    return run, readback
