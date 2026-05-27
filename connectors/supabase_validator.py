"""Supabase connector validator — standalone module."""
import os, urllib.request, urllib.error

def validate(url: str = None, key: str = None) -> dict:
    url = url or os.environ.get("APEX_SUPABASE_URL", "")
    key = key or os.environ.get("APEX_SUPABASE_KEY", "")
    if not url or not key:
        return {"connector": "supabase", "state": "declared", "error": "url or key missing"}
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"connector": "supabase", "state": "action_capable", "status": r.status}
    except urllib.error.HTTPError as e:
        return {"connector": "supabase", "state": "auth_failed", "code": e.code}
    except Exception as e:
        return {"connector": "supabase", "state": "unreachable", "error": str(e)}
