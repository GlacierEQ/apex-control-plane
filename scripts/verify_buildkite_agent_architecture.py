#!/usr/bin/env python3
"""Fail closed when Buildkite agent architecture contradicts verified machine truth."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
ALIASES={"amd64":"x86_64","x64":"x86_64","x86-64":"x86_64","x86_64":"x86_64","aarch64":"arm64","arm64":"arm64"}
def normalize_arch(value: Any)->str:
    raw=str(value or "").strip().lower(); return ALIASES.get(raw,raw)
def verify(receipt:dict[str,Any],expected_arch:str,*,queue:str="macos-self")->dict[str,Any]:
    expected=normalize_arch(expected_arch)
    if not expected: raise ValueError("expected architecture is required")
    resources=receipt.get("resources") if isinstance(receipt.get("resources"),dict) else {}
    ar=resources.get("agents") if isinstance(resources.get("agents"),dict) else {}
    if ar.get("status")!="OBSERVED": return {"status":"UNVERIFIED_AGENT_READBACK","expected_arch":expected,"queue":queue,"matched_agents":0,"contradictions":[]}
    agents=ar.get("items") if isinstance(ar.get("items"),list) else []
    matched=[a for a in agents if isinstance(a,dict) and str(a.get("queue") or "")==queue]
    contradictions=[]; unknown=[]
    for agent in matched:
        observed=normalize_arch(agent.get("arch")); row={"id":agent.get("id"),"name":agent.get("name"),"hostname":agent.get("hostname"),"connection_state":agent.get("connection_state"),"observed_arch":observed or None}
        if not observed: unknown.append(row)
        elif observed!=expected: contradictions.append(row)
    status="ARCHITECTURE_CONTRADICTION" if contradictions else "UNVERIFIED_NO_MATCHING_AGENT" if not matched else "UNVERIFIED_ARCH_MISSING" if unknown else "VERIFIED_MATCH"
    return {"status":status,"expected_arch":expected,"queue":queue,"matched_agents":len(matched),"contradictions":contradictions,"unknown_arch_agents":unknown}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--inventory",type=Path,default=Path("artifacts/buildkite/live-inventory.json")); p.add_argument("--expected-arch",required=True); p.add_argument("--queue",default="macos-self"); p.add_argument("--output",type=Path,default=Path("artifacts/buildkite/agent-architecture-verification.json")); a=p.parse_args()
    result=verify(json.loads(a.inventory.read_text(encoding="utf-8")),a.expected_arch,queue=a.queue); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["status"]=="VERIFIED_MATCH" else 2
if __name__=="__main__": raise SystemExit(main())
