"""Notion connector validator — standalone module."""

import os
import json
import urllib.request
import urllib.error


def validate(token: str = None) -> dict:
    token = token or os.environ.get("APEX_NOTION_TOKEN", "")
    if not token:
        return {"connector": "notion", "state": "declared", "error": "token missing"}
    req = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return {
                "connector": "notion",
                "state": "action_capable",
                "user": data.get("name"),
                "type": data.get("type"),
            }
    except urllib.error.HTTPError as e:
        return {"connector": "notion", "state": "auth_failed", "code": e.code}
    except Exception as e:
        return {"connector": "notion", "state": "unreachable", "error": str(e)}
