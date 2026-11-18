"""Provider adapter tests with in-memory transport; no credential tests or live calls."""
import json
from unittest.mock import patch
import pytest
from src.glaciereq_supabase_graph_provider import fetch_graph


class Response:
    status = 206
    def __init__(self, url, rows):
        self.url = url
        self.rows = rows
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def geturl(self):
        return self.url
    def read(self, size):
        return json.dumps(self.rows).encode()


def node(key):
    return {"source_id": key, "memory_type": "structured_memory_graph_node",
            "metadata": {"graph_id": "GLACIEREQ-MEMGRAPH-V1", "node_key": key}}


def test_authenticated_pagination_and_headers():
    observed = []
    def transport(request, timeout):
        observed.append(request)
        return Response(request.full_url, [node("A")] if len(observed) == 1 else [])
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "test-token"}):
        rows = fetch_graph("https://example.supabase.co", page_size=1, opener=transport)
    assert len(rows) == 1
    assert len(observed) == 2
    assert observed[0].get_header("Authorization") == "Bearer test-token"
    assert observed[0].get_header("Range") == "0-0"
    assert observed[1].get_header("Range") == "1-1"


@pytest.mark.parametrize("url", [
    "http://example.supabase.co", "https://u:p@example.supabase.co",
    "https://example.supabase.co/?token=secret", "https://example.supabase.co/other",
])
def test_reject_url(url):
    with pytest.raises(ValueError, match="HTTPS"):
        fetch_graph(url)


def test_reject_duplicate_pages():
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "test-token"}):
        with pytest.raises(ValueError, match="duplicate"):
            fetch_graph("https://example.supabase.co", page_size=1,
                        opener=lambda request, timeout: Response(request.full_url, [node("A")]))


def test_reject_provider_redirect():
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "test-token"}):
        with pytest.raises(ValueError, match="redirect"):
            fetch_graph("https://example.supabase.co", opener=lambda request, timeout:
                        Response("https://other.example/rest/v1/apex_memories", [node("A")]))


def test_reject_unavailable_authentication():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="authentication unavailable"):
            fetch_graph("https://example.supabase.co")
