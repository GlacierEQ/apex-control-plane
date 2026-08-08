"""Supabase connector validator — standalone module."""

import os
import urllib.error
import urllib.request


def validate(url: str | None = None, key: str | None = None) -> dict:
    url = url or os.environ.get("APEX_SUPABASE_URL", "")
    key = key or os.environ.get("APEX_SUPABASE_KEY", "")
    if not url or not key:
        return {
            "connector": "supabase",
            "state": "declared",
            "error": "url or key missing",
        }
    request = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {
                "connector": "supabase",
                "state": "action_capable",
                "status": response.status,
            }
    except urllib.error.HTTPError as error:
        return {"connector": "supabase", "state": "auth_failed", "code": error.code}
    except (urllib.error.URLError, TimeoutError) as error:
        return {"connector": "supabase", "state": "unreachable", "error": str(error)}
