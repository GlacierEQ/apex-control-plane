import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "verify_buildkite_agent_architecture.py"
spec = importlib.util.spec_from_file_location("verify_buildkite_agent_architecture", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
verify = module.verify


def inventory(status="OBSERVED", agents=None):
    return {"resources": {"agents": {"status": status, "items": agents or []}}}


def agent(arch, queue="macos-self", ident="a1"):
    return {"id": ident, "name": "runner", "hostname": "host", "queue": queue, "arch": arch, "connection_state": "connected"}


def test_aliases_normalize_to_verified_match():
    result = verify(inventory(agents=[agent("amd64")]), "x86_64")
    assert result["status"] == "VERIFIED_MATCH"
    assert result["matched_agents"] == 1


def test_architecture_contradiction_is_explicit_and_source_bearing():
    result = verify(inventory(agents=[agent("arm64")]), "x86_64")
    assert result["status"] == "ARCHITECTURE_CONTRADICTION"
    assert result["contradictions"][0]["observed_arch"] == "arm64"
    assert result["contradictions"][0]["id"] == "a1"


def test_unobserved_provider_state_never_passes():
    result = verify(inventory(status="BLOCKED_NO_AUTHENTICATED_READBACK"), "x86_64")
    assert result["status"] == "UNVERIFIED_AGENT_READBACK"


def test_wrong_queue_never_passes():
    result = verify(inventory(agents=[agent("x86_64", queue="oracle-arm64")]), "x86_64")
    assert result["status"] == "UNVERIFIED_NO_MATCHING_AGENT"


def test_missing_arch_never_passes():
    result = verify(inventory(agents=[agent(None)]), "x86_64")
    assert result["status"] == "UNVERIFIED_ARCH_MISSING"


def test_mixed_matching_queue_fails_on_any_contradiction():
    result = verify(inventory(agents=[agent("x86_64", ident="good"), agent("aarch64", ident="bad")]), "amd64")
    assert result["status"] == "ARCHITECTURE_CONTRADICTION"
    assert result["matched_agents"] == 2
    assert [row["id"] for row in result["contradictions"]] == ["bad"]
