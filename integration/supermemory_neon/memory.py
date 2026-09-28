"""
Supermemory client for apex-control-plane.
Same interface as Pro-DOCTOR-STRANGE/integration/supermemory_neon/memory.py.
Keep in sync or extract to a shared package.
"""

import os
from typing import Optional
from supermemory import Supermemory
from dotenv import load_dotenv

load_dotenv()

_client: Optional[Supermemory] = None


def get_client() -> Supermemory:
    global _client
    if _client is None:
        kwargs = {}
        base_url = os.getenv("SUPERMEMORY_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        _client = Supermemory(**kwargs)
    return _client


def push_connector_summary(connector_id: str, summary: str) -> None:
    """Push a connector health/activity summary to Supermemory."""
    get_client().add(
        container_tag=f"connector:{connector_id}",
        content=summary,
    )


def push_audit_summary(date_str: str, summary: str) -> None:
    """Push the daily audit summary to Supermemory."""
    get_client().add(
        container_tag=f"audit:daily:{date_str}",
        content=summary,
    )


def query_connector(connector_id: str, query: str) -> list[str]:
    """Retrieve recent memory about a connector."""
    profile = get_client().profile(
        container_tag=f"connector:{connector_id}",
        q=query,
        threshold=0.6,
    )
    return [
        r.get("memory", "") if isinstance(r, dict) else str(r)
        for r in (profile.search_results.results or [])
    ]
