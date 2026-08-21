import importlib.util
import json
import sys
import types
from pathlib import Path

if importlib.util.find_spec("rich") is None:
    rich = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")
    rich_panel = types.ModuleType("rich.panel")
    rich_table = types.ModuleType("rich.table")

    class Console:
        def print(self, *_args, **_kwargs):
            pass

    class Panel:
        def __init__(self, *_args, **_kwargs):
            pass

    class Table:
        def __init__(self, *_args, **_kwargs):
            pass

        def add_column(self, *_args, **_kwargs):
            pass

        def add_row(self, *_args, **_kwargs):
            pass

    rich_console.Console = Console
    rich_panel.Panel = Panel
    rich_table.Table = Table
    sys.modules["rich"] = rich
    sys.modules["rich.console"] = rich_console
    sys.modules["rich.panel"] = rich_panel
    sys.modules["rich.table"] = rich_table

import apex_runner
import daily_audit


def test_daily_connector_status_requires_live_validation(monkeypatch):
    monkeypatch.setattr(
        daily_audit,
        "validate_github",
        lambda: {"connector": "github", "state": "auth_failed", "code": 401},
    )
    monkeypatch.setattr(
        daily_audit,
        "validate_notion",
        lambda: {"connector": "notion", "state": "action_capable", "user": "test"},
    )

    results = daily_audit.validate_connectors()

    assert results["github"]["status"] == "RED"
    assert results["github"]["authenticated"] is False
    assert results["github"]["reachable"] is False
    assert results["github"]["action_capable"] is False
    assert results["notion"]["status"] == "GREEN"
    assert results["notion"]["action_capable"] is True


def test_daily_secret_scan_excludes_generated_history_and_redacts_value(tmp_path):
    generated = tmp_path / "audit_logs"
    generated.mkdir()
    credential = "ghp_" + ("A" * 20)
    (generated / "old.json").write_text(credential, encoding="utf-8")

    source = tmp_path / "src"
    source.mkdir()
    (source / "scanner.py").write_text('pattern = "ghp_"\n', encoding="utf-8")

    assert daily_audit.scan_secrets(str(tmp_path)) == []

    leak_path = source / "leak.env"
    leak_path.write_text(f"GITHUB_TOKEN={credential}\n", encoding="utf-8")
    findings = daily_audit.scan_secrets(str(tmp_path))

    assert len(findings) == 1
    assert credential not in findings[0].evidence
    assert "value redacted" in findings[0].evidence


def test_daily_secret_scan_covers_env_variants_uppercase_and_private_keys(tmp_path):
    assert daily_audit._should_scan_secret_file(".env.local")
    assert daily_audit._should_scan_secret_file("CONFIG.ENV")
    assert daily_audit._should_scan_secret_file("server.PEM")

    secret_dir = tmp_path / "config"
    secret_dir.mkdir()
    private_key_header = ("-" * 5) + "BEGIN RSA PRIVATE KEY" + ("-" * 5)
    (secret_dir / "server.PEM").write_text(
        f"{private_key_header}\nredacted-test-body\n",
        encoding="utf-8",
    )

    findings = daily_audit.scan_secrets(str(tmp_path))
    assert len(findings) == 1
    assert "private key" in findings[0].evidence


def test_secret_scanners_cover_password_configuration_forms(tmp_path):
    source = tmp_path / "config"
    source.mkdir()
    password_value = "".join(("hunter", "123"))
    env_key = "DB_" + "PASSWORD"
    yaml_key = "pass" + "word"
    json_key = '"' + yaml_key + '"'

    (source / ".env.local").write_text(
        f"{env_key}={password_value}\n",
        encoding="utf-8",
    )
    (source / "config.yaml").write_text(
        f"{yaml_key}: {password_value}\n",
        encoding="utf-8",
    )
    (source / "config.json").write_text(
        f'{{{json_key}: "{password_value}"}}\n',
        encoding="utf-8",
    )

    daily_findings = daily_audit.scan_secrets(str(tmp_path))
    runner_findings = apex_runner.scan_for_secrets(str(tmp_path))

    assert len(daily_findings) == 3
    assert len(runner_findings) == 3
    assert all("password assignment" in finding.evidence for finding in daily_findings)
    assert all("password assignment" in finding.evidence for finding in runner_findings)


def test_secret_scanners_restore_xai_and_legacy_notion_formats(tmp_path):
    source = tmp_path / "config"
    source.mkdir()
    xai_key = "xai-" + ("X" * 24)
    legacy_notion = "secret_" + ("N" * 24)
    (source / ".env.local").write_text(
        f"XAI_API_KEY={xai_key}\nNOTION_TOKEN={legacy_notion}\n",
        encoding="utf-8",
    )

    daily_findings = daily_audit.scan_secrets(str(tmp_path))
    runner_findings = apex_runner.scan_for_secrets(str(tmp_path))

    assert len(daily_findings) == 2
    assert len(runner_findings) == 2
    assert all(xai_key not in finding.evidence for finding in daily_findings)
    assert all(legacy_notion not in finding.evidence for finding in daily_findings)


def test_daily_drift_accepts_env_github_token_source(tmp_path, monkeypatch):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "safe.yml").write_text(
        "env:\n  GITHUB_TOKEN: ${{ env.GITHUB_TOKEN }}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert daily_audit.detect_drift() == []


def test_daily_drift_validates_each_token_assignment(tmp_path, monkeypatch):
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
    monkeypatch.chdir(tmp_path)

    findings = daily_audit.detect_drift()
    assert len(findings) == 1
    assert "unsafe token source" in findings[0].title


def test_apex_runner_secret_scan_does_not_match_scanner_vocabulary(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "scanner.py").write_text(
        'patterns = ["ghp_", "sk-", "AKIA", "secret_"]\n',
        encoding="utf-8",
    )
    (tmp_path / "audit_log").mkdir()
    generated_credential = "github_pat_" + ("B" * 40)
    (tmp_path / "audit_log" / "old.json").write_text(
        generated_credential,
        encoding="utf-8",
    )

    assert apex_runner.scan_for_secrets(str(tmp_path)) == []

    credential = "sk-" + ("C" * 24)
    leak_path = source / "leak.env"
    leak_path.write_text(f"OPENAI_API_KEY={credential}\n", encoding="utf-8")
    findings = apex_runner.scan_for_secrets(str(tmp_path))

    assert len(findings) == 1
    assert credential not in findings[0].evidence
    assert "value redacted" in findings[0].evidence


def test_apex_runner_uses_repository_probe_for_actions_token(monkeypatch):
    urls = []

    class Response:
        status_code = 200

        def json(self):
            return {"full_name": "GlacierEQ/test-repo"}

    def get(url, *_args, **_kwargs):
        urls.append(url)
        return Response()

    fake_requests = types.SimpleNamespace(RequestException=RuntimeError, get=get)
    monkeypatch.setattr(apex_runner, "requests", fake_requests)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPO", "GlacierEQ/test-repo")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    github = apex_runner.validate_connectors()[0]

    assert urls == ["https://api.github.com/repos/GlacierEQ/test-repo"]
    assert github.authenticated is True
    assert github.reachable is True
    assert github.action_capable is True


def test_apex_runner_degrades_on_malformed_github_json(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return []

    fake_requests = types.SimpleNamespace(
        RequestException=RuntimeError,
        get=lambda *_args, **_kwargs: Response(),
    )
    monkeypatch.setattr(apex_runner, "requests", fake_requests)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPO", "GlacierEQ/test-repo")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    github = apex_runner.validate_connectors()[0]
    assert github.authenticated is False
    assert github.reachable is False
    assert github.action_capable is False
    assert github.notes == "invalid_json_response"


def test_apex_runner_does_not_treat_supabase_404_as_operational(monkeypatch):
    class Response:
        status_code = 404

        def json(self):
            return {}

    fake_requests = types.SimpleNamespace(
        RequestException=RuntimeError,
        get=lambda *_args, **_kwargs: Response(),
    )
    monkeypatch.setattr(apex_runner, "requests", fake_requests)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    supabase = apex_runner.validate_connectors()[2]
    assert supabase.authenticated is False
    assert supabase.reachable is False
    assert supabase.action_capable is False
    assert supabase.notes == "http_status=404"


def test_apex_runner_persists_run_unique_atomic_receipts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = apex_runner.AuditRun(run_id="run-one", timestamp="2026-08-08T00:00:00Z")
    second = apex_runner.AuditRun(run_id="run-two", timestamp="2026-08-08T00:01:00Z")

    first_log, first_queue = apex_runner.persist_run(first)
    second_log, second_queue = apex_runner.persist_run(second)

    assert first_log.exists()
    assert first_queue.exists()
    assert second_log.exists()
    assert second_queue.exists()
    assert first_log != second_log
    assert first_queue != second_queue
    aliases = [
        path
        for path in Path("audit_log").glob("run_*.json")
        if path not in {first_log, second_log}
    ]
    assert len(aliases) == 1
    assert json.loads(aliases[0].read_text(encoding="utf-8"))["run_id"] == "run-two"
    assert not list(Path("audit_log").glob(".*.tmp"))
    assert not list(Path("action_queue").glob(".*.tmp"))


def test_apex_daily_workflow_defers_failure_until_after_durable_receipts():
    workflow = Path(".github/workflows/apex-daily.yml").read_text(encoding="utf-8")

    run_pos = workflow.index("id: apex_audit")
    upload_pos = workflow.index("- name: Upload audit receipt fallback")
    commit_pos = workflow.index("- name: Commit audit results")
    issue_pos = workflow.index("- name: Auto-create issues for P0/P1 findings")
    propagate_pos = workflow.index("- name: Propagate audit result")

    assert run_pos < upload_pos < commit_pos < issue_pos < propagate_pos
    assert workflow.count("if: always()") >= 4
    assert 'echo "status=${audit_status}" >> "$GITHUB_OUTPUT"' in workflow
    assert "group: apex-daily-${{ github.repository }}" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "audit_log/run_${{ github.run_id }}.json" in workflow
    assert "for attempt in 1 2 3" in workflow
    assert 'git fetch --no-tags origin "${target_branch}"' in workflow
    assert 'git rebase "origin/${target_branch}"' in workflow
    issue_step = workflow[issue_pos:propagate_pos]
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in issue_step


def test_ci_checkouts_do_not_persist_tokens_and_shared_gate_is_pinned():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert workflow.count("persist-credentials: false") >= 2
    assert (
        "GlacierEQ/public-actions-runner-host/.github/workflows/reusable-ci.yml@"
        "6757957d290878b1c0831da95328dc29f65d77c9"
    ) in workflow
