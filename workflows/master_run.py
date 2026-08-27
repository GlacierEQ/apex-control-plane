"""
APEX MASTER WORKFLOW RUNNER
Standard: Explicit 15-state Forward Lifecycle Machine with Controlled Side States.
Enforces the Invariant: Only mutation + readback + (expected == observed) advances to COMPLETE.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.changeset import ChangeSet
from contracts.context_pack import ContextPack
from contracts.mission import Mission, MissionStatus
from contracts.receipt import ECHOReceipt
from adapters.echo.store import ECHOStore
from adapters.roottruth.store import RootTruthStore
from verification.state_diff import StateVerifier


class MasterWorkflowRunner:
    """
    Durable workflow state machine executor.
    Coordinates Context Hydration -> Agent Dispatch -> Reconcile -> ChangeSet -> Preflight -> Mutation -> Readback -> Verification -> Receipts.
    """

    def __init__(
        self,
        echo_store: Optional[ECHOStore] = None,
        root_truth: Optional[RootTruthStore] = None,
    ):
        self.echo = echo_store or ECHOStore()
        self.root_truth = root_truth or RootTruthStore()

    def run_mission_cycle(
        self,
        mission: Mission,
        raw_agent_findings: Dict[str, Any],
        proposed_changes: Dict[str, Any],
        system_adapter: Any,
    ) -> Mission:
        """
        Executes the formal 15-stage workflow lifecycle to completion.
        """
        # 1. RECEIVED -> CONTEXT_HYDRATING
        mission.transition_to(MissionStatus.CONTEXT_HYDRATING, "Initiating context hydration")
        context_pack = ContextPack.create(mission.mission_id, mission.correlation_id)

        # Populate context pack from RootTruth
        for k, v in self.root_truth.all_truths().items():
            context_pack.add_fact(f"{k}: {v.get('value')}", "RootTruthStore", verified=True)

        # 2. CONTEXT_LOCKED
        context_pack.lock()
        mission.transition_to(MissionStatus.CONTEXT_LOCKED, "Context pack locked against drift")

        # 3. MISSION_COMPILED
        mission.transition_to(MissionStatus.MISSION_COMPILED, "Mission execution payload compiled")

        # 4. DISPATCHING -> EXECUTING
        mission.transition_to(MissionStatus.DISPATCHING, "Dispatching workers")
        mission.transition_to(MissionStatus.EXECUTING, "Workers executing task")

        # 5. RESULTS_COLLECTING -> RECONCILING
        mission.transition_to(MissionStatus.RESULTS_COLLECTING, "Gathering agent outputs")
        mission.transition_to(MissionStatus.RECONCILING, "Reconciling proposals into ChangeSet")

        # 6. CHANGESET_READY
        changeset = ChangeSet.create(mission.mission_id, mission.correlation_id)
        for target, data in proposed_changes.items():
            changeset.add_operation(
                system=data.get("system", "filesystem"),
                resource=target,
                operation=data.get("operation", "update_file"),
                expected_before=data.get("expected_before", {}),
                desired_after=data.get("desired_after", {}),
            )
        mission.transition_to(MissionStatus.CHANGESET_READY, f"ChangeSet {changeset.changeset_id} prepared")

        # 7. PREFLIGHT
        mission.transition_to(MissionStatus.PREFLIGHT, "Evaluating optimistic concurrency locks")
        for op in changeset.operations:
            # Check preflight against reality
            obs = system_adapter.observe(op.resource)
            exp_head = op.expected_before.get("head_sha")
            if exp_head and exp_head != obs.get("head_sha"):
                mission.transition_to(MissionStatus.BLOCKED, f"Preflight failed: {op.resource} is STALE")
                return mission

        # 8. MUTATING
        mission.transition_to(MissionStatus.MUTATING, "Applying atomic mutations")
        t_start = time.time()
        applied_operations = []
        for op in changeset.operations:
            system_adapter.apply_operation(op)
            applied_operations.append(op)

        # 9. READBACK
        mission.transition_to(MissionStatus.READBACK, "Reading back state from physical storage")
        readbacks = {}
        for op in changeset.operations:
            target_path = op.desired_after.get("path", "")
            rb = system_adapter.readback(op.resource, target_path)
            readbacks[op.resource] = rb

        # 10. VERIFYING (Expected delta == Observed delta)
        mission.transition_to(MissionStatus.VERIFYING, "Verifying mathematical delta match")
        for op in changeset.operations:
            rb = readbacks[op.resource]
            exp_hash = op.desired_after.get("content_hash")
            obs_hash = rb.get("content_hash")

            v_res = StateVerifier.verify_mutation(
                expected_state={"content_hash": exp_hash},
                readback_state={"content_hash": obs_hash},
            )

            if not v_res.is_verified:
                # 1. Trigger COMPENSATING state
                mission.transition_to(
                    MissionStatus.COMPENSATING,
                    f"Triggering automated compensation for {op.resource}: {v_res.discrepancies}",
                )
                # 2. Rollback all applied operations in reverse order
                for applied_op in reversed(applied_operations):
                    if hasattr(system_adapter, "revert_operation"):
                        system_adapter.revert_operation(applied_op)

                # 3. Log ROLLED_BACK receipt in ECHO
                last_rcpt = self.echo.get_last_receipt()
                prev_hash = last_rcpt.receipt_hash if last_rcpt else "GENESIS_ROOT"
                rollback_rcpt = ECHOReceipt.create(
                    mission_id=mission.mission_id,
                    correlation_id=mission.correlation_id,
                    step="changeset.compensate_and_rollback",
                    started_at=t_start,
                    expected_state={"operations_count": len(changeset.operations)},
                    observed_state={"compensated_count": len(applied_operations)},
                    external_ids={"changeset_id": changeset.changeset_id},
                    result="ROLLED_BACK",
                    previous_receipt_hash=prev_hash,
                    inputs_payload={"reason": v_res.discrepancies},
                )
                self.echo.append_receipt(rollback_rcpt)

                # 4. Transition to FAILED
                mission.transition_to(
                    MissionStatus.FAILED,
                    f"Verification failed on {op.resource}: {v_res.discrepancies}. All changes rolled back.",
                )
                return mission

        # 11. COMMITTING_STATE (ECHO Receipt + RootTruth)
        mission.transition_to(MissionStatus.COMMITTING_STATE, "Writing immutable hash-chained receipt")
        last_rcpt = self.echo.get_last_receipt()
        prev_hash = last_rcpt.receipt_hash if last_rcpt else "GENESIS_ROOT"

        receipt = ECHOReceipt.create(
            mission_id=mission.mission_id,
            correlation_id=mission.correlation_id,
            step="changeset.apply_and_verify",
            started_at=t_start,
            expected_state={"operations_count": len(changeset.operations)},
            observed_state={"verified_count": len(readbacks)},
            external_ids={"changeset_id": changeset.changeset_id},
            result="VERIFIED",
            previous_receipt_hash=prev_hash,
            inputs_payload=changeset.to_dict(),
        )
        self.echo.append_receipt(receipt)

        # Update RootTruth
        for op in changeset.operations:
            self.root_truth.set(
                entity_key=f"{op.system}:{op.resource}",
                value={"status": "UPDATED", "path": op.desired_after.get("path")},
                provenance_receipt_id=receipt.receipt_id,
            )

        # 12. COMPLETE (Only reached after readback == expected)
        mission.transition_to(MissionStatus.COMPLETE, "Mission verified and committed to reality")
        return mission
