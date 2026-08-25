#!/usr/bin/env python3
"""Verify that an exact GitHub commit carries the expected Buildkite status projection."""
from __future__ import annotations
import argparse, json, os, re, urllib.error, urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

BUILDKITE_URL_RE=re.compile(r"^https://buildkite\.com/([^/]+)/([^/]+)/builds/(\d+)(?:/.*)?$")

@dataclass(frozen=True)
class Projection:
    status: str
    context: str
    state: str | None
    target_url: str | None
    organization: str | None
    pipeline: str | None
    build_number: int | None


def reconcile(payload: dict[str,Any], expected_context: str) -> Projection:
    statuses=payload.get("statuses") or []
    matches=[s for s in statuses if isinstance(s,dict) and s.get("context")==expected_context]
    if not matches:
        return Projection("MISSING", expected_context, None, None, None, None, None)
    status=matches[0]; state=str(status.get("state") or "")
    target=status.get("target_url")
    if state != "success":
        return Projection("NON_SUCCESS", expected_context, state, target, None, None, None)
    m=BUILDKITE_URL_RE.match(str(target or ""))
    if not m:
        return Projection("INVALID_TARGET", expected_context, state, target, None, None, None)
    org,pipeline,number=m.groups()
    return Projection("VERIFIED_SUCCESS_PROJECTION", expected_context, state, target, org, pipeline, int(number))


def fetch_status(repo:str, sha:str, token:str) -> dict[str,Any]:
    req=urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/{sha}/status",headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","User-Agent":"GlacierEQ-APEX-Buildkite-Master/1"})
    try:
        with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub status read failed HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}") from exc


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--repo",required=True); p.add_argument("--sha",required=True); p.add_argument("--context",required=True); p.add_argument("--input",type=Path); p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.input: payload=json.loads(a.input.read_text())
    else:
        token=os.getenv("GITHUB_TOKEN","").strip()
        if not token: print("GITHUB_TOKEN required when --input is omitted"); return 2
        payload=fetch_status(a.repo,a.sha,token)
    result={"schema":"glaciereq.apex.buildkite-github-projection.v1","repository":a.repo,"commit":a.sha,**asdict(reconcile(payload,a.context))}
    if a.output: a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["status"]=="VERIFIED_SUCCESS_PROJECTION" else 1
if __name__=="__main__": raise SystemExit(main())
