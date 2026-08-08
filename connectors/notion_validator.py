"""Notion connector validator — standalone module."""

import json
import os
import urllib.error
import urllib.request


def validate(token: str | None = None) -> dict:
    token = token or os.environ.get("APEX_NOTION_TOKEN", "")
    if not token:
        return {"connector": "notion", "state": "declared", "error": "token missing"}
    request = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read())
            return {
                "connector": "notion",
                "state": "action_capable",
                "user": data.get("name"),
                "type": data.get("type"),
            }
    except urllib.error.HTTPError as error:
        return {"connector": "notion", "state": "auth_failed", "code": error.code}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"connector": "notion", "state": "unreachable", "error": str(error)}
