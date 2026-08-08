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
    password_value = "hunter" + "123"
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
