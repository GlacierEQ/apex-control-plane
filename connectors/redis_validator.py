"""Redis connector validator — TCP reachability, no redis-py required."""

import os
import socket
from urllib.parse import urlparse


def validate(redis_url: str | None = None) -> dict:
    redis_url = redis_url or os.environ.get("APEX_REDIS_URL", "")
    if not redis_url:
        return {
            "connector": "redis",
            "state": "declared",
            "error": "APEX_REDIS_URL not set",
        }
    try:
        parsed = urlparse(redis_url)
        host = parsed.hostname
        if not host:
            raise ValueError("Redis URL is missing a hostname")
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=5):
            pass
        return {"connector": "redis", "state": "reachable", "host": host, "port": port}
    except (OSError, TypeError, ValueError) as error:
        return {"connector": "redis", "state": "unreachable", "error": str(error)}
