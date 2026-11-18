"""Integration tests for runnable durable agent work units."""
import sys

from src.agent_work_runner import main, run_work_unit


def test_real_subprocess_runs_once_across_restart(tmp_path):
    db = tmp_path / "state.sqlite"
    marker = tmp_path / "marker.txt"
    command = [
        sys.executable, "-c",
        "from pathlib import Path; p=Path(__import__('sys').argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x')",
        str(marker),
    ]
    first = run_work_unit(db, "job-1", "write marker", command)
    assert first["state"] == "succeeded"
    assert first["result"]["returncode"] == 0
    assert marker.read_text() == "x"
    second = run_work_unit(db, "job-1", "write marker", command)
    assert second["state"] == "already_claimed:succeeded"
    assert marker.read_text() == "x"


def test_failed_command_never_replays_automatically(tmp_path):
    db = tmp_path / "state.sqlite"
    command = [sys.executable, "-c", "raise SystemExit(9)"]
    first = run_work_unit(db, "job-failed", "failure", command)
    assert first["state"] == "needs_reconciliation"
    assert first["result"]["returncode"] == 9
    second = run_work_unit(db, "job-failed", "failure", command)
    assert second["state"] == "already_claimed:needs_reconciliation"


def test_cli_prints_json_and_executes(tmp_path, capsys):
    code = main([
        "--database", str(tmp_path / "cli.sqlite"),
        "--workload-id", "cli-1", "--objective", "hello",
        "--command", sys.executable, "-c", "print('hello')",
    ])
    assert code == 0
    assert '"state": "succeeded"' in capsys.readouterr().out


def test_same_workload_id_cannot_run_different_command(tmp_path):
    import pytest

    db = tmp_path / "identity.sqlite"
    first = [sys.executable, "-c", "print('first')"]
    second = [sys.executable, "-c", "print('second')"]
    assert run_work_unit(db, "identity-1", "same description", first)["state"] == "succeeded"
    with pytest.raises(ValueError, match="different objective"):
        run_work_unit(db, "identity-1", "same description", second)


def test_readback_persists_across_new_executor_instances(tmp_path):
    import json

    db = tmp_path / "readback.sqlite"
    command = [sys.executable, "-c", "print('persisted')"]
    first = run_work_unit(db, "readback-1", "readback", command)
    assert first["state"] == "succeeded"
    assert first["durable_record"]["state"] == "succeeded"
    assert first["durable_record"]["result"]["attempted"] == ["local_process"]
    replay = run_work_unit(db, "readback-1", "readback", command)
    assert replay["durable_record"]["state"] == "succeeded"
    assert replay["state"] == "already_claimed:succeeded"
    from src.agent_work_runner import main
    from io import StringIO
    from contextlib import redirect_stdout
    output = StringIO()
    with redirect_stdout(output):
        assert main(["--database", str(db), "--workload-id", "readback-1", "--readback"]) == 0
    record = json.loads(output.getvalue())
    assert record["state"] == "succeeded"
    assert record["result"]["status"] == "success"
    assert "persisted" in record["result"]["provider_result"]["stdout"]


def test_readback_missing_claim_is_non_success(tmp_path):
    from src.agent_work_runner import main
    assert main([
        "--database", str(tmp_path / "empty.sqlite"),
        "--workload-id", "unknown", "--readback",
    ]) == 1


def test_failed_subprocess_evidence_survives_restart(tmp_path):
    from src.durable_agent_executor import DurableAgentExecutor

    db = tmp_path / "failed.sqlite"
    result = run_work_unit(
        db, "failure-evidence", "capture failure",
        [sys.executable, "-c", "import sys; print('diagnostic'); sys.exit(7)"],
    )
    assert result["state"] == "needs_reconciliation"
    assert result["result"]["returncode"] == 7
    assert "diagnostic" in result["result"]["stdout"]
    record = DurableAgentExecutor(db).readback("failure-evidence")
    assert record["result"]["provider_result"]["returncode"] == 7


def test_timeout_change_rejected_before_reexecution(tmp_path):
    import pytest

    db = tmp_path / "timeout-identity.sqlite"
    command = [sys.executable, "-c", "print('done')"]
    assert run_work_unit(db, "timeout-identity", "same objective", command, timeout_seconds=5)["state"] == "succeeded"
    with pytest.raises(ValueError, match="different objective"):
        run_work_unit(db, "timeout-identity", "same objective", command, timeout_seconds=6)


def test_invalid_command_and_timeout_do_not_create_claim(tmp_path):
    import pytest
    from src.durable_agent_executor import DurableAgentExecutor

    db = tmp_path / "invalid.sqlite"
    for argv, timeout in [(["echo", 1], 3), ([], 3), (["echo"], True), (["echo"], 0)]:
        with pytest.raises(ValueError):
            run_work_unit(db, "invalid-1", "invalid", argv, timeout_seconds=timeout)
    assert DurableAgentExecutor(db).readback("invalid-1") is None


def test_concurrent_workers_invoke_subprocess_at_most_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db = tmp_path / "concurrent.sqlite"
    marker = tmp_path / "calls.txt"
    command = [
        sys.executable, "-c",
        "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]);"
        "f=p.open('a'); f.write('called\\n'); f.close(); time.sleep(0.2)",
        str(marker),
    ]
    gate = Barrier(6)

    def worker(_):
        gate.wait()
        return run_work_unit(db, "shared-claim", "single side effect", command)["state"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        states = list(pool.map(worker, range(6)))
    assert states.count("succeeded") == 1
    assert all(s == "succeeded" or s.startswith("already_claimed:") for s in states)
    assert marker.read_text().splitlines() == ["called"]
