from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_DIR = ROOT / "supabase" / "functions"


def test_node_worker_auth_runtime_suite() -> None:
    node = shutil.which("node")
    assert node is not None, "node runtime is required to execute Edge Function worker auth tests"
    proc = subprocess.run(
        [node, "--test", str(ROOT / "tests" / "worker_auth_runtime.test.mts")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"node --test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


@pytest.mark.parametrize(
    "fn_name",
    [
        "apex-github-batch-worker",
        "apex-github-webhook-worker",
        "apex-github-router",
        "apex-github-connector",
        "connector-health-ping",
        "legal-case-orchestrator",
        "legal-deadline-monitor",
        "operator-impact-context",
    ],
)
def test_privileged_edge_workers_enforce_auth_before_body_or_db_access(fn_name: str) -> None:
    source = (FUNCTIONS_DIR / fn_name / "index.ts").read_text(encoding="utf-8")
    assert '../_shared/worker_auth.ts' in source
    serve_idx = source.index("Deno.serve")
    serve_tail = source[serve_idx:]
    assert "requirePrivilegedWorkerAuth" in serve_tail
    auth_idx = serve_tail.index("requirePrivilegedWorkerAuth")

    for body_or_db_marker in (
        "req.text(",
        "req.json(",
        "readJson(req)",
        "admin.rpc(",
        "admin.from(",
        "supabase.rpc(",
        "supabase.from(",
        "db.rpc(",
        "db.from(",
    ):
        if body_or_db_marker in serve_tail:
            assert auth_idx < serve_tail.index(body_or_db_marker), (
                f"{fn_name} must enforce requirePrivilegedWorkerAuth before {body_or_db_marker}"
            )
