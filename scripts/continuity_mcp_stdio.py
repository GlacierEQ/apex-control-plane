#!/usr/bin/env python3
"""Opt-in stdio MCP adapter for the verified owner-local mission consumer.

No native ChatGPT auto-invocation claim: MCP clients must register and call this tool.
No network listener, credentials, filesystem writes outside existing mission entry.
"""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.mission_enter import enter

PROTOCOL = "2025-03-26"
TOOL = "glaciereq_recover_mission_context"

def _tool_definition():
    return {"name": TOOL, "description": "Recover and independently verify the GLACIEREQ mission cursor and source evidence before substantive execution.",
            "inputSchema": {"type": "object", "properties": {
                "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "invocation_id": {"type": "string", "minLength": 1, "maxLength": 128}},
                "required": ["session_id", "invocation_id"], "additionalProperties": False}}

def _config():
    keys = ("GLACIEREQ_CONTINUITY_PROFILE", "GLACIEREQ_CONTINUITY_OUTPUT_DIR",
            "GLACIEREQ_CONTINUITY_DATABASE")
    values = [os.environ.get(key) for key in keys]
    if not all(values):
        raise ValueError("owner-local continuity configuration missing")
    return [Path(value).expanduser().resolve(strict=True) for value in values]

def _valid_identifier(value):
    return (isinstance(value, str) and 0 < len(value) <= 128
            and all(c.isascii() and (c.isalnum() or c in "-_ .") for c in value)
            and value == value.strip())

def handle(request, *, recover=None):
    recover = enter if recover is None else recover
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        raise ValueError("invalid JSON-RPC envelope")
    method, params = request.get("method"), request.get("params", {})
    if method == "notifications/initialized":
        return None
    if not isinstance(params, dict):
        raise ValueError("invalid params")
    if method == "initialize":
        return {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                "serverInfo": {"name": "glaciereq-continuity-owner", "version": "0.1.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [_tool_definition()]}
    if method != "tools/call" or params.get("name") != TOOL:
        raise ValueError("unsupported MCP method or tool")
    args = params.get("arguments")
    if (not isinstance(args, dict) or set(args) != {"session_id", "invocation_id"}
            or not all(_valid_identifier(v) for v in args.values())):
        raise ValueError("invalid mission invocation identifiers")
    profile, output_dir, database = _config()
    if not profile.is_file() or not output_dir.is_dir() or not database.is_file():
        raise ValueError("existing owner-private mission state required")
    result = recover(owner_script=Path(__file__).with_name("run_owned_continuity.py"),
                     profile=profile, output_dir=output_dir, database=database, **args)
    if result.get("status") != "MISSION_CONTEXT_READY":
        raise ValueError("mission recovery not verified")
    return {"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}],
            "structuredContent": result, "isError": False}

def serve(input_stream=sys.stdin, output_stream=sys.stdout):
    for line in input_stream:
        try:
            request = json.loads(line)
            request_id = request.get("id") if isinstance(request, dict) else None
            result = handle(request)
            if request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
            response = {"jsonrpc": "2.0", "id": request_id if "request_id" in locals() else None,
                        "error": {"code": -32603, "message": "continuity request rejected"}}
            print(type(exc).__name__ + ": " + str(exc)[:300], file=sys.stderr)
        output_stream.write(json.dumps(response, sort_keys=True) + "\n")
        output_stream.flush()


if __name__ == "__main__":
    serve()
