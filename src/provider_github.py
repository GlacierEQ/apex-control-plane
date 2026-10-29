"""Live GitHub Contents API adapter for the gate-free operational core.

Write authority is the supplied GitHub token's permissions. Completion requires
independent readback from GitHub; no secrets are written into code or receipts.
"""
from __future__ import annotations
import base64
import json
import re
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GitHubContentsAdapter:
    idempotent = True

    def __init__(self, token: str, *, api_base: str = "https://api.github.com"):
        if not isinstance(token, str) or not token:
            raise ValueError("GitHub access token is required from the authorized host")
        if not api_base.startswith("https://"):
            raise ValueError("GitHub API requires HTTPS")
        self._token = token
        self._base = api_base.rstrip("/")

    def _resource(self, payload: Mapping[str, Any]) -> str:
        repo = payload["repo"]
        path = payload["path"]
        if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("repo must be owner/name")
        if not isinstance(path, str) or not path or path.startswith("/") or any(x in {"", ".", ".."} for x in path.split("/")):
            raise ValueError("invalid GitHub repository file path")
        return f"{self._base}/repos/{repo}/contents/{quote(path, safe='/')}"

    def _branch(self, payload: Mapping[str, Any]) -> str:
        branch = payload.get("branch", "main")
        if not isinstance(branch, str) or not branch or branch.startswith("-"):
            raise ValueError("invalid branch name")
        return branch

    def _request(self, method: str, url: str, body: dict | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "glaciereq-operational-core",
            "Content-Type": "application/json",
        })
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))

    def _existing(self, payload: Mapping[str, Any]) -> tuple[bytes, str] | None:
        url = self._resource(payload) + "?ref=" + quote(self._branch(payload), safe="")
        try:
            response = self._request("GET", url)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if response.get("type") != "file" or response.get("encoding") != "base64":
            raise ValueError("GitHub did not return a base64 file")
        content = base64.b64decode(response["content"], validate=False)
        return content, response["sha"]

    def execute(self, payload: Mapping[str, Any], operation_id: str) -> dict[str, Any]:
        content = payload["content"]
        if not isinstance(content, str):
            raise ValueError("content must be text")
        expected = content.encode("utf-8")
        previous = self._existing(payload)
        if previous is not None and previous[0] == expected:
            return {"state": "already_satisfied", "provider": "github"}
        body = {
            "branch": self._branch(payload),
            "message": str(payload.get("message") or f"Execute {operation_id}"),
            "content": base64.b64encode(expected).decode("ascii"),
        }
        if previous is not None:
            body["sha"] = previous[1]
        response = self._request("PUT", self._resource(payload), body)
        return {"state": "written", "provider": "github",
                "commit": response.get("commit", {}).get("sha")}

    def verify(self, payload: Mapping[str, Any]) -> bool | None:
        try:
            current = self._existing(payload)
        except (HTTPError, OSError, ValueError, KeyError, TypeError):
            return None
        return current is not None and current[0] == str(payload["content"]).encode("utf-8")
