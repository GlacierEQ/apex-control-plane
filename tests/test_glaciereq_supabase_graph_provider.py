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


def test_rejects_arbitrary_https_host_before_token_transport():
    invoked = []
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        with pytest.raises(ValueError, match="untrusted provider host"):
            fetch_graph("https://attacker.example", opener=lambda *args, **kwargs: invoked.append(args))
    assert not invoked


def test_custom_domain_requires_exact_explicit_pin():
    invoked = []
    with patch.dict("os.environ", {
        "GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only",
        "GLACIEREQ_SUPABASE_EXPECTED_HOST": "memory.example.org",
    }, clear=True):
        with pytest.raises(ValueError, match="configured pin"):
            fetch_graph("https://other.example.org", opener=lambda *args, **kwargs: invoked.append(args))
        assert len(fetch_graph("https://memory.example.org",
            opener=lambda request, timeout: Response(request.full_url, [node("A")]))) == 1
    assert not invoked


@pytest.mark.parametrize("url", [
    "https://example.supabase.co:444", "https://example.supabase.co.evil.org",
    "https://supabase.co", "https://sub.sub.supabase.co",
])
def test_rejects_host_confusion(url):
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        with pytest.raises(ValueError, match="untrusted provider host"):
            fetch_graph(url)


def test_rejects_foreign_origin_with_identical_path_and_query():
    # A hostile transport may preserve the path and query while changing origin.
    # The previous split('?')[0] check accepted this response.
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        def transport(request, timeout):
            return Response(request.full_url.replace("example.supabase.co", "evil.supabase.co"), [node("A")])
        with pytest.raises(ValueError, match="redirect refused"):
            fetch_graph("https://example.supabase.co", opener=transport)


def test_rejects_query_modified_response_url():
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        with pytest.raises(ValueError, match="redirect refused"):
            fetch_graph("https://example.supabase.co", opener=lambda request, timeout:
                        Response(request.full_url + "&tampered=1", [node("A")]))


def test_rejects_partial_page_when_provider_advertises_more_rows():
    class PartialResponse(Response):
        headers = {"Content-Range": "0-0/3"}
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        with pytest.raises(ValueError, match="truncated page"):
            fetch_graph("https://example.supabase.co", page_size=2,
                        opener=lambda request, timeout: PartialResponse(request.full_url, [node("A")]))


def test_rejects_inconsistent_provider_content_range():
    class IncorrectRange(Response):
        headers = {"Content-Range": "1-1/1"}
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        with pytest.raises(ValueError, match="disagrees"):
            fetch_graph("https://example.supabase.co", page_size=2,
                        opener=lambda request, timeout: IncorrectRange(request.full_url, [node("A")]))


def test_accepts_complete_short_final_page_with_content_range():
    class FinalResponse(Response):
        headers = {"Content-Range": "0-0/1"}
    with patch.dict("os.environ", {"GLACIEREQ_SUPABASE_ACCESS_TOKEN": "fixture-only"}, clear=True):
        result = fetch_graph("https://example.supabase.co", page_size=2,
                             opener=lambda request, timeout: FinalResponse(request.full_url, [node("A")]))
    assert [r["source_id"] for r in result] == ["A"]
