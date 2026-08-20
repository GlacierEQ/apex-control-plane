"""Read-only, capability-preserving branch synthesis inventory.

The current default head is always the synthesis floor. Branches with unique
commits are donors, diverged donors are fresh-synthesis candidates, and only
fully reachable branches become retirement candidates. This module never
mutates refs and never emits file contents or patches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DATE_END = re.compile(r"[-_](?:20\d{2}[-_]?(?:0[1-9]|1[0-2])[-_]?(?:0[1-9]|[12]\d|3[01])|20\d{6})$")
HEX_END = re.compile(r"[-_][0-9a-f]{7,40}$", re.I)
VERSION_END = re.compile(r"[-_]v\d+(?:[-_.]\d+)*$", re.I)
ITERATION_END = frozenset({"active","actual","build","check","code","exec","final","impl","live","only","patch","real","run","ship","work","write"})
MAX_BRANCHES = 1000
MAX_PATHS = 300
PATH_SIGNALS = (
    (re.compile(r"(^|/)(tests?|specs?)(/|$)", re.I), 5, "tests"),
    (re.compile(r"(^|/)(evidence|forensic|timeline|contradiction|docket)(/|$)", re.I), 7, "legal-intelligence"),
    (re.compile(r"\.(py|ts|tsx|js|jsx|rs|go|java|kt|swift|rb|cs|cpp|c|h)$", re.I), 4, "executable-code"),
    (re.compile(r"(^|/)(workflows?|\.github/workflows)(/|$)", re.I), 3, "automation"),
    (re.compile(r"(^|/)(schemas?|contracts?|interfaces?)(/|$)", re.I), 3, "interfaces"),
)

class BranchSynthesisError(RuntimeError):
    pass

class GitHubReader(Protocol):
    def repository(self, repository: str) -> Mapping[str, Any]: ...
    def branches(self, repository: str) -> list[Mapping[str, Any]]: ...
    def compare(self, repository: str, base: str, head: str) -> Mapping[str, Any]: ...

class GitHubAPI:
    """Bounded read-only GitHub REST adapter."""
    def __init__(self, token: str | None = None, *, api_url: str = "https://api.github.com", timeout: float = 20):
        self.token = (token or "").strip(); self.api_url = api_url.rstrip("/"); self.timeout = timeout

    def _request(self, url: str) -> urllib.request.Request:
        headers = {"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"GlacierEQ-Branch-Synthesis/1"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        return urllib.request.Request(url, headers=headers, method="GET")

    def _read(self, url: str) -> tuple[Any, Mapping[str, str]]:
        try:
            with urllib.request.urlopen(self._request(url), timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8")), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BranchSynthesisError(f"GitHub GET failed with HTTP {exc.code}: {body[:240]}") from exc
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BranchSynthesisError(f"GitHub GET failed: {exc}") from exc

    @staticmethod
    def _identity(repository: str) -> tuple[str, str]:
        if not REPO_RE.fullmatch(repository): raise BranchSynthesisError(f"invalid repository identity: {repository!r}")
        return tuple(repository.split("/", 1))  # type: ignore[return-value]

    def _path(self, repository: str, suffix: str = "") -> str:
        owner, name = self._identity(repository)
        return f"repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}{suffix}"

    def repository(self, repository: str) -> Mapping[str, Any]:
        payload, _ = self._read(f"{self.api_url}/{self._path(repository)}")
        if not isinstance(payload, Mapping): raise BranchSynthesisError(f"{repository} metadata was not an object")
        return payload

    def branches(self, repository: str) -> list[Mapping[str, Any]]:
        url: str | None = f"{self.api_url}/{self._path(repository, '/branches')}?per_page=100"; rows = []
        while url:
            payload, headers = self._read(url)
            if not isinstance(payload, list): raise BranchSynthesisError(f"{repository} branch listing was not an array")
            rows.extend(row for row in payload if isinstance(row, Mapping))
            if len(rows) > MAX_BRANCHES: raise BranchSynthesisError(f"{repository} exceeds {MAX_BRANCHES} branches")
            url = _next_link(headers.get("Link") or headers.get("link"))
        return rows

    def compare(self, repository: str, base: str, head: str) -> Mapping[str, Any]:
        suffix = f"/compare/{urllib.parse.quote(base, safe='')}...{urllib.parse.quote(head, safe='')}"
        payload, _ = self._read(f"{self.api_url}/{self._path(repository, suffix)}")
        if not isinstance(payload, Mapping): raise BranchSynthesisError(f"{repository}:{head} comparison was not an object")
        return payload

@dataclass(frozen=True)
class BranchInventory:
    name: str; head_sha: str; protected: bool; family: str; relation: str; action: str
    ahead_by: int; behind_by: int; changed_paths: tuple[str, ...]; changed_paths_truncated: bool
    capability_signals: tuple[str, ...]; priority_score: float; reasons: tuple[str, ...]

@dataclass(frozen=True)
class RepositoryInventory:
    repository: str; default_branch: str; default_head_sha: str; branch_count: int
    donor_count: int; absorbed_count: int; review_required_count: int
    preservation_set: tuple[str, ...]; retirement_candidates: tuple[str, ...]
    branch_families: Mapping[str, tuple[str, ...]]; branches: tuple[BranchInventory, ...]
    inventory_sha256: str

def _valid_repo(repository: str) -> None:
    if not REPO_RE.fullmatch(repository): raise BranchSynthesisError(f"invalid repository identity: {repository!r}")

def _sha(value: Any, label: str) -> str:
    sha = str(value or "").lower()
    if not SHA_RE.fullmatch(sha): raise BranchSynthesisError(f"invalid {label} SHA: {value!r}")
    return sha

def _count(value: Any, label: str) -> int:
    try: parsed = int(value or 0)
    except (TypeError, ValueError) as exc: raise BranchSynthesisError(f"invalid {label}: {value!r}") from exc
    if parsed < 0: raise BranchSynthesisError(f"invalid {label}: {parsed}")
    return parsed

def _next_link(header: str | None) -> str | None:
    if not header: return None
    for chunk in header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', chunk)
        if match and match.group(2) == "next": return match.group(1)
    return None

def branch_family_key(name: str) -> str:
    """Groups likely siblings only; family membership never authorizes deletion."""
    parts = name.split("/"); original = parts[-1].strip().casefold(); leaf = original
    while True:
        before = leaf
        for pattern in (DATE_END, HEX_END, VERSION_END): leaf = pattern.sub("", leaf)
        tokens = [token for token in re.split(r"[-_]+", leaf) if token]
        while tokens and tokens[-1] in ITERATION_END: tokens.pop()
        leaf = "-".join(tokens)
        if leaf == before: break
    stem = leaf or original; prefix = "/".join(part.casefold() for part in parts[:-1])
    return f"{prefix}/{stem}" if prefix else stem

def _paths(payload: Mapping[str, Any]) -> tuple[tuple[str, ...], bool]:
    files = payload.get("files")
    if files is None: return (), False
    if not isinstance(files, list): raise BranchSynthesisError("comparison files must be an array")
    paths = {str(row.get("filename") or "").strip() for row in files[:MAX_PATHS] if isinstance(row, Mapping)}
    return tuple(sorted(filter(None, paths), key=str.casefold)), len(files) > MAX_PATHS

def _signals(paths: Iterable[str]) -> tuple[tuple[str, ...], float]:
    found: set[str] = set(); score = 0.0
    for path in paths:
        for pattern, weight, signal in PATH_SIGNALS:
            if pattern.search(path): found.add(signal); score += weight
    return tuple(sorted(found)), min(score, 40.0)

def _relation(status: str, ahead: int, behind: int) -> tuple[str, str, tuple[str, ...], float]:
    status = status.casefold().strip()
    if status == "identical": return "IDENTICAL", "RETIRE_AFTER_REACHABILITY_PROOF", ("head equals current default",), 0
    if status == "behind" and ahead == 0: return "ABSORBED", "RETIRE_AFTER_REACHABILITY_PROOF", ("no unique commits; head is reachable from current default",), 0
    if status == "ahead" and ahead > 0 and behind == 0: return "FORWARD_DONOR", "PRESERVE_AND_SYNTHESIZE", (f"{ahead} unique commit(s) beyond current default",), 30
    if status == "diverged" and ahead > 0 and behind > 0: return "DIVERGED_DONOR", "PRESERVE_AND_FRESH_SYNTHESIZE", (f"{ahead} unique commit(s)", f"missing {behind} newer default commit(s); wholesale merge is unsafe"), 40
    return "REVIEW_REQUIRED", "PRESERVE_PENDING_REVIEW", (f"ambiguous compare state {status!r}: ahead={ahead}, behind={behind}",), 20

def _branch(reader: GitHubReader, repository: str, default: str, default_sha: str, raw: Mapping[str, Any]) -> BranchInventory:
    name = str(raw.get("name") or "").strip(); commit = raw.get("commit")
    if not name or not isinstance(commit, Mapping): raise BranchSynthesisError(f"{repository} returned malformed branch metadata")
    head = _sha(commit.get("sha"), f"{repository}:{name} head"); protected = bool(raw.get("protected")); family = branch_family_key(name)
    if name == default:
        if head != default_sha: raise BranchSynthesisError(f"{repository}:{default} default-head sources disagree")
        return BranchInventory(name, head, protected, family, "BASELINE", "KEEP_BASELINE", 0, 0, (), False, (), 0, ("current default head is the synthesis floor",))
    payload = reader.compare(repository, default, name); ahead = _count(payload.get("ahead_by"), "ahead_by"); behind = _count(payload.get("behind_by"), "behind_by")
    relation, action, reasons, base_score = _relation(str(payload.get("status") or "UNKNOWN"), ahead, behind)
    paths, truncated = _paths(payload); signals, path_score = _signals(paths)
    return BranchInventory(name, head, protected, family, relation, action, ahead, behind, paths, truncated, signals, round(base_score + min(ahead, 20) + path_score + (2 if protected else 0), 2), reasons)

def _digest(repository: str, default: str, default_sha: str, rows: Iterable[BranchInventory]) -> str:
    payload = {"repository":repository,"default_branch":default,"default_head_sha":default_sha,"branches":[asdict(row) for row in rows]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def inventory_repository(reader: GitHubReader, repository: str) -> RepositoryInventory:
    _valid_repo(repository); repo = reader.repository(repository); default = str(repo.get("default_branch") or "").strip()
    if not default: raise BranchSynthesisError(f"{repository} did not expose a default branch")
    raw = reader.branches(repository)
    if len(raw) > MAX_BRANCHES: raise BranchSynthesisError(f"{repository} exceeds {MAX_BRANCHES} branches")
    names = [str(row.get("name") or "").strip() for row in raw]
    if len(names) != len(set(names)): raise BranchSynthesisError(f"{repository} branch listing contains duplicate names")
    defaults = [row for row in raw if str(row.get("name") or "").strip() == default]
    if len(defaults) != 1 or not isinstance(defaults[0].get("commit"), Mapping): raise BranchSynthesisError(f"{repository} expected one valid default branch row")
    default_sha = _sha(defaults[0]["commit"].get("sha"), f"{repository} default")
    embedded = repo.get("default_branch_commit")
    if isinstance(embedded, Mapping) and _sha(embedded.get("sha"), f"{repository} default") != default_sha: raise BranchSynthesisError(f"{repository} default-head sources disagree")
    rows = tuple(sorted((_branch(reader, repository, default, default_sha, row) for row in raw), key=lambda row: (-row.priority_score, row.name.casefold())))
    preserve_actions = {"PRESERVE_AND_SYNTHESIZE","PRESERVE_AND_FRESH_SYNTHESIZE","PRESERVE_PENDING_REVIEW"}
    preserve = tuple(sorted((row.name for row in rows if row.action in preserve_actions), key=str.casefold)); retire = tuple(sorted((row.name for row in rows if row.action == "RETIRE_AFTER_REACHABILITY_PROOF"), key=str.casefold))
    families: dict[str, list[str]] = {}
    for row in rows: families.setdefault(row.family, []).append(row.name)
    families_out = {key:tuple(sorted(members,key=str.casefold)) for key,members in sorted(families.items()) if len(members)>1}
    return RepositoryInventory(repository, default, default_sha, len(rows), sum(row.relation in {"FORWARD_DONOR","DIVERGED_DONOR"} for row in rows), sum(row.relation in {"IDENTICAL","ABSORBED"} and row.name != default for row in rows), sum(row.relation == "REVIEW_REQUIRED" for row in rows), preserve, retire, families_out, rows, _digest(repository, default, default_sha, rows))

def _report_repository(row: RepositoryInventory) -> dict[str, Any]:
    payload = asdict(row)
    safe_branches = []
    for branch in row.branches:
        item = asdict(branch)
        paths = item.pop("changed_paths")
        item["changed_path_count"] = len(paths)
        safe_branches.append(item)
    payload["branches"] = safe_branches
    return payload

def synthesis_report(inventories: Iterable[RepositoryInventory]) -> dict[str, Any]:
    rows = sorted(inventories, key=lambda row: row.repository.casefold())
    return {"schema":"APEX_BRANCH_SYNTHESIS_V1","generated_at":datetime.now(timezone.utc).isoformat(),"semantics":{"baseline":"current default is the floor","preservation":"unique/diverged/ambiguous branches remain donors until composed","retirement":"only reachable heads qualify; this tool never mutates refs","privacy":"changed paths are used in-memory for scoring but suppressed from reports; no source bytes or legal narratives"},"repository_count":len(rows),"branch_count":sum(row.branch_count for row in rows),"donor_count":sum(row.donor_count for row in rows),"absorbed_count":sum(row.absorbed_count for row in rows),"review_required_count":sum(row.review_required_count for row in rows),"repositories":[_report_repository(row) for row in rows]}

def write_report(path: str | Path, payload: Mapping[str, Any]) -> None:
    destination = Path(path); destination.parent.mkdir(parents=True, exist_ok=True); temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name); json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_path, destination); temp_path = None
    finally:
        if temp_path is not None: temp_path.unlink(missing_ok=True)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a capability-preserving branch synthesis manifest")
    parser.add_argument("--repo", action="append", required=True, help="owner/name; repeat for multiple repositories"); parser.add_argument("--output", required=True); parser.add_argument("--token-env", default="APEX_GITHUB_TOKEN"); parser.add_argument("--api-url", default="https://api.github.com"); args = parser.parse_args(argv)
    client = GitHubAPI(os.environ.get(args.token_env) or os.environ.get("GITHUB_TOKEN"), api_url=args.api_url)
    try: write_report(args.output, synthesis_report(inventory_repository(client, repo) for repo in dict.fromkeys(args.repo)))
    except (BranchSynthesisError, OSError) as exc: print(f"ERROR: {exc}", file=sys.stderr); return 1
    return 0

if __name__ == "__main__": raise SystemExit(main())
