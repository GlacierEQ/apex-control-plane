"""GitHub connector validator — standalone module."""

import json
import os
import urllib.error
import urllib.request


def validate(token: str | None = None, owner: str = "GlacierEQ") -> dict:
    del owner
    token = token or os.environ.get("APEX_GITHUB_TOKEN", "")
    if not token:
        return {"connector": "github", "state": "declared", "error": "token missing"}
    request = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read())
            return {
                "connector": "github",
                "state": "action_capable",
                "login": data.get("login"),
                "repos": data.get("public_repos"),
            }
    except urllib.error.HTTPError as error:
        return {"connector": "github", "state": "auth_failed", "code": error.code}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"connector": "github", "state": "unreachable", "error": str(error)}
