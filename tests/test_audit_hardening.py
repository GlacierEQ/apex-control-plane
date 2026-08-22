import json
import types
from pathlib import Path

import apex_issue_writer
import apex_runner
import audit_engine
import daily_audit


def test_connector_probe_never_promotes_reachability_to_action_authority(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"full_name": "GlacierEQ/test-repo"}

    fake_requests = types.SimpleNamespace(
        RequestException=RuntimeError,
        get=lambda *_args, **_kwargs: Response(),
    )
    monkeypatch.setattr(audit_engine, "requests", fake_requests)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPO", "GlacierEQ/test-repo")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    github = apex_runner.validate_connectors()[0]
    assert github.authenticated is True
    assert github.reachable is True
    assert github.receipt_verified is False
    assert github.action_authorized is False
    assert github.action_capable is False
    assert github.state() == "REACHABLE_NON_AUTHORIZING"


def test_daily_compatibility_surface_uses_same_non_authorizing_engine(monkeypatch):
    monkeypatch.setattr(
        apex_runner,
        "validate_connectors",
        lambda: [
            apex_runner.ConnectorStatus(name="GitHub", declared=True),
            apex_runner.ConnectorStatus(
                name="Notion", declared=True, authenticated=True, reachable=True
            ),
        ],
    )
    results = daily_audit.validate_connectors()
    assert results["github"]["status"] == "RED"
    assert results["notion"]["status"] == "AMBER"
    assert results["notion"]["action_capable"] is False
    assert results["notion"]["action_authorized"] is False


def test_secret_scan_excludes_generated_history_and_redacts_values(tmp_path):
    generated = tmp_path / "audit_log"
    generated.mkdir()
    credential = "ghp_" + ("A" * 20)
    (generated / "old.json").write_text(credential, encoding="utf-8")
    source = tmp_path / "src"
    source.mkdir()
    leak_path = source / ".env.local"
    leak_path.write_text(f"GITHUB_TOKEN={credential}\n", encoding="utf-8")

    findings = apex_runner.scan_for_secrets(str(tmp_path))
    assert len(findings) == 1
    assert credential not in findings[0].evidence
    assert "value redacted" in findings[0].evidence


def test_secret_scan_covers_password_xai_notion_and_private_key_forms(tmp_path):
    source = tmp_path / "config"
    source.mkdir()
    password_value = "hunter" + "123"
    xai_key = "xai-" + ("X" * 24)
    legacy_notion = "secret_" + ("N" * 24)
    private_key_header = ("-" * 5) + "BEGIN RSA PRIVATE KEY" + ("-" * 5)
    (source / ".env.local").write_text(
        (
            f"DB_PASSWORD={password_value}\n"
            f"XAI_API_KEY={xai_key}\n"
            f"NOTION_TOKEN={legacy_notion}\n"
        ),
        encoding="utf-8",
    )
    (source / "server.PEM").write_text(private_key_header, encoding="utf-8")

    findings = apex_runner.scan_for_secrets(str(tmp_path))
    evidence = " ".join(finding.evidence for finding in findings)
    assert len(findings) == 2
    assert password_value not in evidence
    assert xai_key not in evidence
    assert legacy_notion not in evidence
    assert private_key_header not in evidence


def test_workflow_drift_validates_every_token_assignment(tmp_path):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "mixed.yml").write_text(
        "env:\n"
        "  GITHUB_TOKEN: ${{ github.token }}\n"
        "jobs:\n"
        "  unsafe:\n"
        "    env:\n"
        "      GITHUB_TOKEN: legacy-token-alias\n",
        encoding="utf-8",
    )
    findings = apex_runner.detect_workflow_drift(str(tmp_path))
    assert len(findings) == 1
    assert "unsafe token source" in findings[0].title


def test_persist_and_verify_are_run_exact_atomic_and_digest_bound(tmp_path):
    run = apex_runner.AuditRun(
        run_id="run-one",
        started_at="2026-08-22T16:00:00Z",
        completed_at="2026-08-22T16:00:01Z",
        source_sha="abc123",
        status="clean",
    )
    log_path, queue_path, proof_path = apex_runner.persist_run(run, tmp_path)
    readback = apex_runner.verify_run_receipt("run-one", tmp_path)

    assert log_path == readback.log_path
    assert queue_path == readback.queue_path
    assert proof_path == readback.proof_path
    assert readback.source_sha == "abc123"
    assert readback.status == "clean"
    assert readback.external_action_authorized is False
    assert not list(tmp_path.rglob("*.tmp"))


def test_readback_rejects_tampered_log(tmp_path):
    run = apex_runner.AuditRun(
        run_id="tamper",
        started_at="2026-08-22T16:00:00Z",
        completed_at="2026-08-22T16:00:01Z",
        status="clean",
    )
    log_path, _, _ = apex_runner.persist_run(run, tmp_path)
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    payload["run"]["status"] = "findings"
    log_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        apex_runner.verify_run_receipt("tamper", tmp_path)
    except apex_runner.AuditInvariantError as error:
        assert "digest mismatch" in str(error)
    else:
        raise AssertionError("tampered audit log passed readback")


def test_execute_audit_persists_then_reads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_engine, "validate_connectors", list)
    (tmp_path / ".env.example").write_text("A=\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")

    run, readback = audit_engine.execute_audit(
        run_id="exact-123",
        root=tmp_path,
        source_sha="deadbeef",
        workflow_run_id="123",
    )
    assert run.run_id == "exact-123"
    assert readback.run_id == "exact-123"
    assert readback.source_sha == "deadbeef"
    assert readback.status == "clean"


def test_issue_writer_refuses_newest_file_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "action_queue").mkdir()
    (tmp_path / "action_queue" / "queue_old.json").write_text("[]", encoding="utf-8")
    assert apex_issue_writer.main(["--run-id", "missing"]) == 2


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeGitHubRequests:
    def __init__(self):
        self.RequestException = RuntimeError
        self.issues = []
        self.comments = {}
        self.next_comment_id = 100

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        del headers, timeout
        if url.endswith("/issues") and method == "GET":
            return _FakeResponse(200, list(self.issues))
        if url.endswith("/issues") and method == "POST":
            issue = {"number": 7, "title": json["title"], "body": json["body"]}
            self.issues.append(issue)
            return _FakeResponse(201, dict(issue))
        if url.endswith("/issues/7/comments") and method == "GET":
            return _FakeResponse(200, list(self.comments.values()))
        if url.endswith("/issues/7/comments") and method == "POST":
            self.next_comment_id += 1
            comment = {"id": self.next_comment_id, "body": json["body"]}
            self.comments[comment["id"]] = comment
            return _FakeResponse(201, dict(comment))
        if "/issues/comments/" in url:
            comment_id = int(url.rsplit("/", 1)[1])
            if method == "PATCH":
                self.comments[comment_id]["body"] = json["body"]
                return _FakeResponse(200, dict(self.comments[comment_id]))
            if method == "GET":
                return _FakeResponse(200, dict(self.comments[comment_id]))
        if url.endswith("/issues/7"):
            if method == "PATCH":
                self.issues[0]["body"] = json["body"]
                return _FakeResponse(200, dict(self.issues[0]))
            if method == "GET":
                return _FakeResponse(200, dict(self.issues[0]))
        raise AssertionError(f"unexpected fake GitHub request: {method} {url} {params}")


def test_audit_ledger_is_exact_idempotent_and_read_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = apex_runner.AuditRun(
        run_id="123",
        started_at="2026-08-22T16:00:00Z",
        completed_at="2026-08-22T16:00:01Z",
        source_sha="deadbeef",
        status="clean",
    )
    apex_runner.persist_run(run)
    fake = _FakeGitHubRequests()
    monkeypatch.setattr(apex_issue_writer, "requests", fake)

    assert apex_issue_writer.publish_run(run_id="123", token="token", repo="x/y") == 0
    assert len(fake.issues) == 1
    assert len(fake.comments) == 1
    only_comment = next(iter(fake.comments.values()))
    assert "<!-- apex-audit-run:123 -->" in only_comment["body"]
    assert "deadbeef" in only_comment["body"]
    assert "External action authorized by audit:** `false`" in only_comment["body"]

    assert apex_issue_writer.publish_run(run_id="123", token="token", repo="x/y") == 0
    assert len(fake.issues) == 1
    assert len(fake.comments) == 1


def test_only_one_scheduled_audit_workflow_remains():
    workflows = Path(".github/workflows")
    assert not (workflows / "daily-audit.yml").exists()
    workflow = (workflows / "apex-daily.yml").read_text(encoding="utf-8")
    assert "Verify exact run receipt and local readback" in workflow
    assert "Publish and read back durable audit ledger" in workflow
    assert "audit_log/proof_${{ github.run_id }}.json" in workflow
    assert "if-no-files-found: error" in workflow
    assert "retention-days: 90" in workflow
    assert "RUN_DATE: ${{ github.run_id }}" in workflow
    assert 'python apex_issue_writer.py --run-id "${RUN_DATE}"' in workflow
    assert "persist-credentials: false" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
