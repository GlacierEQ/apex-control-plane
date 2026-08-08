from pathlib import Path

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


def test_apex_daily_workflow_defers_failure_until_after_receipt_steps():
    workflow = Path(".github/workflows/apex-daily.yml").read_text(encoding="utf-8")

    run_pos = workflow.index("id: apex_audit")
    commit_pos = workflow.index("- name: Commit audit results")
    issue_pos = workflow.index("- name: Auto-create issues for P0/P1 findings")
    propagate_pos = workflow.index("- name: Propagate audit result")

    assert run_pos < commit_pos < issue_pos < propagate_pos
    assert workflow.count("if: always()") >= 3
    assert 'echo "status=${audit_status}" >> "$GITHUB_OUTPUT"' in workflow
