"""GitHub connector validator — standalone module."""
import os, json, urllib.request, urllib.error

def validate(token: str = None, owner: str = "GlacierEQ") -> dict:
    token = token or os.environ.get("APEX_GITHUB_TOKEN", "")
    if not token:
        return {"connector": "github", "state": "declared", "error": "token missing"}
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return {"connector": "github", "state": "action_capable",
                    "login": data.get("login"), "repos": data.get("public_repos")}
    except urllib.error.HTTPError as e:
        return {"connector": "github", "state": "auth_failed", "code": e.code}
    except Exception as e:
        return {"connector": "github", "state": "unreachable", "error": str(e)}
