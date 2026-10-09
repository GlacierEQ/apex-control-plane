"""Independent-process, provider-native readback recovery contract."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap

import pytest
from src.mission_resume import MissionCheckpointStore, ResumeError


def mission():
    return dict(mission_id="HI-157:recovery-smoke", operator_objective="Continue existing mission without repeated acts", desired_outcome="Provable interruption-safe continuation", tasks=[
        {"id": "verified", "order": 1, "deps": [], "key": "smoke:verified", "provider": "fixture", "expected": "receipt exists"},
        {"id": "interrupted", "order": 2, "deps": ["verified"], "key": "smoke:interrupted", "provider": "fixture", "expected": "one side effect"},
        {"id": "continue", "order": 3, "deps": ["interrupted"], "key": "smoke:continue", "provider": "fixture", "expected": "continue at unfinished"},
    ])


class NativeProvider:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS effects (key TEXT PRIMARY KEY, receipt TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (key TEXT NOT NULL)")

    def act(self, key):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO attempts VALUES (?)", (key,))
            db.execute("INSERT OR IGNORE INTO effects VALUES (?,?)", (key, f"native:{key}"))

    def lookup(self, key, expected):
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT receipt FROM effects WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def attempts(self, key):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT COUNT(*) FROM attempts WHERE key=?", (key,)).fetchone()[0]

    def count(self, key):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT COUNT(*) FROM effects WHERE key=?", (key,)).fetchone()[0]


def test_restart_recovers_verified_action_and_does_not_replay(tmp_path):
    storefile, providerfile = tmp_path / 'state.db', tmp_path / 'provider.db'
    native = NativeProvider(providerfile)
    first = MissionCheckpointStore(storefile)
    first.initialize(**mission())
    native.act('smoke:verified')
    assert first.resume('agent-a', native.lookup)['task_id'] == 'interrupted'
    native.act('smoke:interrupted')  # crash before checkpoint: no first.record_verified()

    # A fresh independent Python interpreter must load ONLY persisted source.
    script = textwrap.dedent('''
    import sqlite3, sys
    from src.mission_resume import MissionCheckpointStore
    class Provider:
        def lookup(self, key, expected):
            with sqlite3.connect(sys.argv[2]) as db:
                r=db.execute("SELECT receipt FROM effects WHERE key=?",(key,)).fetchone()
            return r[0] if r else None
    s=MissionCheckpointStore(sys.argv[1]); p=Provider()
    task=s.resume('agent-b',p.lookup)
    if task:
        with sqlite3.connect(sys.argv[2]) as db:
            db.execute("INSERT INTO attempts VALUES (?)",(task['idempotency_key'],))
            db.execute("INSERT OR IGNORE INTO effects VALUES (?,?)",(task['idempotency_key'],'native:'+task['idempotency_key']))
    print(task['task_id'] if task else 'NONE')
    ''')
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH': str(root)}
    proc = subprocess.run([sys.executable, '-c', script, str(storefile), str(providerfile)], cwd=root, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == 'continue'
    assert native.count('smoke:interrupted') == 1
    assert native.attempts('smoke:interrupted') == 1
    assert native.attempts('smoke:continue') == 1
    third = subprocess.run([sys.executable, '-c', script, str(storefile), str(providerfile)], cwd=root, env=env, text=True, capture_output=True)
    assert third.returncode == 0, third.stderr
    assert third.stdout.strip() == 'NONE'
    assert native.attempts('smoke:interrupted') == 1
    assert native.attempts('smoke:continue') == 1
    state = MissionCheckpointStore(storefile)
    assert state.task_state('interrupted') == 'VERIFIED_STEP'
    assert state.task_receipt('interrupted') == 'native:smoke:interrupted'
    assert state.mission_state() == 'ACTIVE'  # L4 proof != L1 success


def test_missing_provider_proof_never_replays_ambiguous_claim(tmp_path):
    native = NativeProvider(tmp_path/'provider.db')
    store = MissionCheckpointStore(tmp_path/'state.db')
    store.initialize(**mission())
    native.act('smoke:verified')
    assert store.resume('agent-a',native.lookup)['task_id']=='interrupted'
    assert store.resume('agent-b',native.lookup) is None  # unresolved claimed task; no duplicate action
    assert store.task_state('interrupted') == 'NEEDS_PROOF'
    assert store.task_state('continue') == 'READY'
    assert store.mission_state() == 'ACTIVE'


def test_existing_state_not_overwritten_by_new_agent(tmp_path):
    store = MissionCheckpointStore(tmp_path/'state.db')
    store.initialize(**mission())
    with pytest.raises(ResumeError, match='mismatch'):
        altered = mission(); altered['operator_objective']='new fake mission'; store.initialize(**altered)
    assert store.task_state('verified')=='READY'


def test_dependency_cycle_refused_without_mutating_original(tmp_path):
    store = MissionCheckpointStore(tmp_path/'state.db')
    broken=mission(); broken['tasks'][0]['deps']=['continue']
    with pytest.raises(ResumeError,match='cycle'):
        store.initialize(**broken)
    store.initialize(**mission())
    assert store.task_state('verified')=='READY'


def test_unavailable_provider_only_blocks_affected_route(tmp_path):
    store = MissionCheckpointStore(tmp_path / 'state.db')
    native = NativeProvider(tmp_path / 'provider.db')
    plan = mission()
    plan['tasks'] = [
        {"id": "offline", "order": 1, "deps": [], "key": "smoke:offline", "provider": "offline-provider", "expected": "write"},
        {"id": "parallel", "order": 2, "deps": [], "key": "smoke:parallel", "provider": "fixture", "expected": "write"},
    ]
    store.initialize(**plan)

    def mixed(key, expected):
        if key == 'smoke:offline':
            raise ConnectionError('provider down, reality unknown')
        return native.lookup(key, expected)

    assert store.resume('agent-c', mixed)['task_id'] == 'parallel'
    assert store.task_state('offline') == 'READY'
    assert store.task_state('parallel') == 'IN_FLIGHT'



def test_stale_readback_cannot_reclassify_another_workers_new_claim(tmp_path):
    """Worker A reads READY; B claims; A must not convert B's live claim to NEEDS_PROOF."""
    native = NativeProvider(tmp_path / "provider.db")
    native.act("smoke:verified")
    first = MissionCheckpointStore(tmp_path / "state.db")
    second = MissionCheckpointStore(tmp_path / "state.db")
    first.initialize(**mission())
    interleaved = []

    def delayed_readback(key, expected):
        if key == "smoke:interrupted" and not interleaved:
            reserved = second.resume("worker-b", native.lookup)
            interleaved.append(reserved)
        return native.lookup(key, expected)

    first.resume("worker-a", delayed_readback)
    assert interleaved[0]["task_id"] == "interrupted"
    assert second.task_state("interrupted") == "IN_FLIGHT"
    with sqlite3.connect(tmp_path / "state.db") as db:
        assert db.execute(
            "SELECT claimed_by FROM tasks WHERE task_id='interrupted'"
        ).fetchone()[0] == "worker-b"
    assert native.attempts("smoke:interrupted") == 0


def test_parallel_resumers_atomically_reserve_only_one_worker(tmp_path):
    """Two independent store objects racing to claim a READY action never both win."""
    from concurrent.futures import ThreadPoolExecutor

    native = NativeProvider(tmp_path / "provider.db")
    native.act("smoke:verified")
    db_path = tmp_path / "state.db"
    MissionCheckpointStore(db_path).initialize(**mission())

    def recover(agent):
        return MissionCheckpointStore(db_path).resume(agent, native.lookup)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, ("worker-a", "worker-b")))
    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1
    assert claimed[0]["task_id"] == "interrupted"
    assert MissionCheckpointStore(db_path).task_state("interrupted") in {
        "IN_FLIGHT", "NEEDS_PROOF"
    }
    assert native.attempts("smoke:interrupted") == 0



def test_two_missions_share_store_but_require_exact_source_scope(tmp_path):
    """Shared checkpoint backend cannot accidentally move another mission's cursor."""
    path = tmp_path / "state.db"
    first_plan = mission()
    second_plan = mission()
    second_plan["mission_id"] = "HI-157:other-front"
    for task in second_plan["tasks"]:
        task["id"] = "other-" + task["id"]
        task["key"] = "other-" + task["key"]
        task["deps"] = ["other-" + dep for dep in task["deps"]]
    MissionCheckpointStore(path).initialize(**first_plan)
    MissionCheckpointStore(path).initialize(**second_plan)
    native = NativeProvider(tmp_path / "provider.db")
    native.act("smoke:verified")
    with pytest.raises(ResumeError, match="explicit mission selection"):
        MissionCheckpointStore(path).resume("unspecified-agent", native.lookup)
    scoped_first = MissionCheckpointStore(path, mission_id=first_plan["mission_id"])
    scoped_second = MissionCheckpointStore(path, mission_id=second_plan["mission_id"])
    assert scoped_first.resume("agent-a", native.lookup)["task_id"] == "interrupted"
    assert scoped_second.resume("agent-b", native.lookup)["task_id"] == "other-verified"
    assert scoped_first.task_state("interrupted") == "IN_FLIGHT"
    assert scoped_second.task_state("other-verified") == "IN_FLIGHT"
    with pytest.raises(ResumeError, match="unknown task"):
        scoped_first.task_state("other-verified")


def test_ambiguous_claim_requires_native_idempotency_guarantee_before_rearm(tmp_path):
    """Recover a confirmed retry-safe task while keeping blind retries impossible."""
    db = tmp_path / "state.db"
    native = NativeProvider(tmp_path / "provider.db")
    native.act("smoke:verified")
    store = MissionCheckpointStore(db)
    store.initialize(**mission())
    assert store.resume("agent-a", native.lookup)["task_id"] == "interrupted"
    assert store.resume("agent-b", native.lookup) is None
    assert store.task_state("interrupted") == "NEEDS_PROOF"
    with pytest.raises(ResumeError, match="idempotency"):
        store.rearm_after_provider_guarantee(
            "interrupted", provider_idempotency_ref="", readback=native.lookup
        )
    assert store.task_state("interrupted") == "NEEDS_PROOF"
    assert store.rearm_after_provider_guarantee(
        "interrupted",
        provider_idempotency_ref="provider-native:fixture/idempotency-key-enforced",
        readback=native.lookup,
    ) == "READY"
    assert store.resume("agent-b", native.lookup)["task_id"] == "interrupted"
    assert native.attempts("smoke:interrupted") == 0


def test_rearm_finds_late_native_receipt_instead_of_reexecuting(tmp_path):
    """If the old worker finally completed, repair the cursor without a second call."""
    native = NativeProvider(tmp_path / "provider.db")
    native.act("smoke:verified")
    store = MissionCheckpointStore(tmp_path / "state.db")
    store.initialize(**mission())
    store.resume("agent-a", native.lookup)
    store.resume("agent-b", native.lookup)
    assert store.task_state("interrupted") == "NEEDS_PROOF"
    native.act("smoke:interrupted")
    assert store.rearm_after_provider_guarantee(
        "interrupted",
        provider_idempotency_ref="provider-native:fixture/idempotency-key-enforced",
        readback=native.lookup,
    ) == "VERIFIED_STEP"
    assert store.resume("agent-c", native.lookup)["task_id"] == "continue"
    assert native.attempts("smoke:interrupted") == 1
    assert store.mission_state() == "ACTIVE"
