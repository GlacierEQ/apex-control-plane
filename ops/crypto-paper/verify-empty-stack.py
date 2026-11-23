#!/usr/bin/env python3
"""End-to-end proof for an unfunded Condor + Hummingbot API deployment.

Read-only assertions. Exit non-zero unless *all* services communicate,
the local model can actually generate, and no trading credentials or bots exist.
No exchange API key, wallet, or account balance is required or accepted.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url: str, method: str = "GET", payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, method=method, data=body)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urlopen(request, timeout=15) as result:
            return json.load(result)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Failed read-only readiness check at {url}: {exc}") from exc


def verify():
    api = os.environ.get("PAPER_API_URL", "http://127.0.0.1:8000").rstrip("/")
    condor = os.environ.get("PAPER_CONDOR_URL", "http://127.0.0.1:8088").rstrip("/")
    model = os.environ.get("PAPER_MODEL_URL", "http://127.0.0.1:11434").rstrip("/")
    user = os.environ["PAPER_API_USER"]
    password = os.environ["PAPER_API_PASSWORD"]
    credential = base64.b64encode(f"{user}:{password}".encode()).decode()
    auth = {"Authorization": f"Basic {credential}"}

    accounts = request_json(f"{api}/accounts/", headers=auth)
    if not isinstance(accounts, list):
        raise AssertionError("API accounts response is not a list")
    for account in accounts:
        # Any configured exchange key defeats the definition of 'unfunded/isolated'.
        keys = request_json(f"{api}/accounts/{account}/credentials", headers=auth)
        if keys != []:
            raise AssertionError(f"Account {account!r} has trading credentials: refuse READY")

    portfolio = request_json(
        f"{api}/portfolio/state",
        method="POST",
        payload={"refresh": False, "skip_gateway": True},
        headers=auth,
    )
    if not isinstance(portfolio, dict):
        raise AssertionError("Hummingbot API portfolio response is invalid")
    for account_data in portfolio.values():
        if not isinstance(account_data, dict):
            raise AssertionError("Unrecognized account balance structure")
        for connector_balances in account_data.values():
            if not isinstance(connector_balances, list):
                raise AssertionError("Unrecognized connector balance structure")
            for balance in connector_balances:
                if not isinstance(balance, dict):
                    raise AssertionError("Unrecognized asset balance structure")
                for key in ("units", "available_units", "total_balance", "available_balance", "usd_value"):
                    if key in balance and float(balance[key] or 0) != 0:
                        raise AssertionError("Nonzero asset balance in unfunded API: refuse READY")

    bots = request_json(f"{api}/bot-orchestration/status", headers=auth)
    if bots.get("status") != "success" or bots.get("data"):
        raise AssertionError("API reports a running bot, or its status is not healthy")

    mqtt = request_json(f"{api}/bot-orchestration/mqtt", headers=auth)
    if mqtt.get("data", {}).get("mqtt_connected") is not True:
        raise AssertionError("Hummingbot broker is not connected")

    if request_json(f"{condor}/api/v1/auth/mode") != {"mode": "local"}:
        raise AssertionError("Condor is not in loopback-only local mode")
    login = request_json(f"{condor}/api/v1/auth/local-login", method="POST", payload={})
    token = login.get("token")
    if not token:
        raise AssertionError("Condor local login did not issue a session")
    bearer = {"Authorization": f"Bearer {token}"}
    servers = request_json(f"{condor}/api/v1/servers", headers=bearer)
    if not isinstance(servers, list) or len(servers) != 1:
        raise AssertionError("Condor must contain precisely one configured paper API")
    if servers[0].get("name") != "paper" or servers[0].get("online") is not True:
        raise AssertionError("Condor cannot reach/authenticate its paper Hummingbot API")
    status = request_json(f"{condor}/api/v1/servers/paper/status", headers=bearer)
    if status.get("status") != "online":
        raise AssertionError("Condor's own server probe did not report online")

    tags = request_json(f"{model}/api/tags")
    if not any(m.get("name", "").startswith("qwen3:0.6b") for m in tags.get("models", [])):
        raise AssertionError("No pinned free local model is loaded")
    generation = request_json(
        f"{model}/api/generate",
        method="POST",
        payload={
            "model": "qwen3:0.6b",
            "prompt": "Reply with the single word READY.",
            "stream": False,
            "think": False,
            "options": {"num_predict": 70},
        },
    )
    if not generation.get("done") or not generation.get("response", "").strip():
        raise AssertionError("Local AI model failed actual inference")

    print(
        "EMPTY_STACK_READY: API authenticated; broker connected; "
        "Condor dashboard authenticated and API online; local model generated; "
        "ZERO exchange credentials, ZERO asset balances and ZERO trading bots."
    )


if __name__ == "__main__":
    try:
        verify()
    except (AssertionError, RuntimeError, KeyError) as exc:
        print(f"EMPTY_STACK_NOT_READY: {exc}", file=sys.stderr)
        sys.exit(1)
