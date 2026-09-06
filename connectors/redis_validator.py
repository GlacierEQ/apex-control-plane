"""Redis connector validator — TCP reachability, no redis-py required."""

import os
import socket
from urllib.parse import urlparse


def validate(redis_url: str = None) -> dict:
    redis_url = redis_url or os.environ.get("APEX_REDIS_URL", "")
    if not redis_url:
        return {
            "connector": "redis",
            "state": "declared",
            "error": "APEX_REDIS_URL not set",
        }
    try:
        p = urlparse(redis_url)
        host = p.hostname
        port = p.port or 6379
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        return {"connector": "redis", "state": "reachable", "host": host, "port": port}
    except Exception as e:
        return {"connector": "redis", "state": "unreachable", "error": str(e)}
