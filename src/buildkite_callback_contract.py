"""Fail-closed Buildkite callback compatibility contract."""
from __future__ import annotations
import hmac
from typing import Any, Mapping
_ALLOWED_STATES={"passed","failed","canceled","running","blocked","scheduled"}
_ALLOWED_EVENTS={"build.finished","build.running","build.scheduled"}
def verify_webhook_token(received_token:str, expected_token:str)->bool:
    return bool(received_token and expected_token and hmac.compare_digest(expected_token,received_token))
def parse_buildkite_callback(payload:Mapping[str,Any])->dict[str,Any]:
    if not isinstance(payload,Mapping): raise ValueError("payload must be a mapping")
    event=payload.get("event"); build=payload.get("build"); pipeline=payload.get("pipeline")
    if event not in _ALLOWED_EVENTS: raise ValueError("explicit recognized event required")
    if not isinstance(build,Mapping) or not isinstance(pipeline,Mapping): raise ValueError("build and pipeline required")
    meta=build.get("meta_data")
    if not isinstance(meta,Mapping): raise ValueError("build.meta_data required")
    fields={"pipeline":pipeline.get("slug"),"build_number":build.get("number"),"commit_sha":build.get("commit"),"state":build.get("state"),"mission_id":meta.get("mission_id"),"correlation_id":meta.get("correlation_id")}
    if any(v is None or v=="" for v in fields.values()): raise ValueError("explicit callback correlation required")
    if not isinstance(fields["build_number"],int) or fields["build_number"]<=0: raise ValueError("valid build_number required")
    if fields["state"] not in _ALLOWED_STATES: raise ValueError("recognized state required")
    return {"event":event,**fields,"passed_observed":fields["state"]=="passed","terminal_provider_verified":False,"authority":"callback_observation_only"}
