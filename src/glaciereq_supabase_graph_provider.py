"""Read GLACIEREQ graph from the configured Supabase PostgREST provider.

Authentication is supplied by the owning runtime via environment, never stored
in source. No credential probes, mutations, or implicit project discovery.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

GRAPH_ID = "GLACIEREQ-MEMGRAPH-V1"
FIELDS = "source_id,memory_type,content,metadata,authority_status"


def fetch_graph(url, *, token_env="GLACIEREQ_SUPABASE_ACCESS_TOKEN", page_size=500,
                opener=None):
    if not isinstance(url, str):
        raise ValueError("invalid provider URL")
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") not in ("", "/rest/v1")):
        raise ValueError("expected exact HTTPS Supabase project base or /rest/v1 URL")
    # Never send a bearer token to an arbitrary caller-supplied HTTPS host.
    # Custom Supabase domains require an explicit, exact runtime host pin.
    hostname = parsed.hostname.lower()
    pinned = os.environ.get("GLACIEREQ_SUPABASE_EXPECTED_HOST", "").lower().strip()
    if pinned:
        if hostname != pinned or parsed.port not in (None, 443):
            raise ValueError("provider host does not match configured pin")
    elif (not hostname.endswith(".supabase.co") or hostname.count(".") != 2
          or parsed.port not in (None, 443)):
        raise ValueError("untrusted provider host; configure an exact host pin")
    if not isinstance(page_size, int) or not 1 <= page_size <= 1000:
        raise ValueError("invalid page size")
    token = os.environ.get(token_env, "")
    if not token or "\n" in token or "\r" in token:
        raise ValueError("configured provider authentication unavailable")
    base = url.rstrip("/")
    if not base.endswith("/rest/v1"):
        base += "/rest/v1"
    params = urllib.parse.urlencode({
        "select": FIELDS,
        "metadata->>graph_id": "eq." + GRAPH_ID,
        "order": "source_id.asc",
    })
    endpoint = base + "/apex_memories?" + params
    rows = []
    seen = set()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("provider redirect refused")

    transport = opener or urllib.request.build_opener(NoRedirect()).open
    for start in range(0, 100000, page_size):
        request = urllib.request.Request(endpoint, headers={
            "Authorization": "Bearer " + token,
            "apikey": token,
            "Range-Unit": "items",
            "Range": f"{start}-{start + page_size - 1}",
            "Accept": "application/json",
        })
        with transport(request, timeout=20) as response:
            # Compare the complete origin, path and query, not just the path.
            # An injected/custom transport must never turn a foreign-host response
            # into apparently authenticated Supabase provenance.
            if response.geturl() != endpoint:
                raise ValueError("provider redirect refused: response URL mismatch")
            status = response.status
            if status not in (200, 206):
                raise ValueError("provider returned unexpected status")
            payload = response.read(4_000_001)
            if len(payload) > 4_000_000:
                raise ValueError("provider page too large")
        page = json.loads(payload)
        if not isinstance(page, list) or len(page) > page_size:
            raise ValueError("invalid provider page")
        for row in page:
            if not isinstance(row, dict):
                raise ValueError("invalid provider row")
            meta = row.get("metadata")
            if (not isinstance(meta, dict) or meta.get("graph_id") != GRAPH_ID
                    or row.get("memory_type") != "structured_memory_graph_node"):
                raise ValueError("provider graph filter mismatch")
            source = row.get("source_id")
            if not isinstance(source, str) or not source or source in seen:
                raise ValueError("duplicate or missing provider source")
            seen.add(source)
            rows.append(row)
        if len(page) < page_size:
            if not rows:
                raise ValueError("empty provider graph")
            return rows
    raise ValueError("provider graph exceeds pagination limit")
