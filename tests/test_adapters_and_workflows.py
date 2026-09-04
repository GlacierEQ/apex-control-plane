"""
APEX CONTROL PLANE: ADAPTERS & OCI PROVISIONER TEST SUITE (L2 VERIFICATION)
Standard: Validates Buildkite verification forge, Notion cockpit sync, Dropbox artifact store, and OCI cloud provisioning.
"""

import hashlib
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from contracts.mission import Mission, MissionStatus, advance_to
from adapters.buildkite.adapter import BuildkiteAdapter
from api.webhooks.buildkite import process_buildkite_event
from adapters.notion.adapter import NotionCockpitAdapter
from adapters.dropbox.adapter import DropboxArtifactAdapter
from infrastructure.oci.provision_temporal_cloud_server import OCITemporalProvisioner


class TestAdaptersAndWorkflows(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="apex_adapters_test_"))
        self.dropbox_mount = self.test_dir / "dropbox_mock"
        self.dropbox_mount.mkdir(parents=True, exist_ok=True)

        self.buildkite = BuildkiteAdapter(api_token="test_bk_token", org_slug="glaciereq")
        self.notion = NotionCockpitAdapter(api_key="test_notion_key", database_id="test_db_id")
        self.dropbox = DropboxArtifactAdapter(token="test_dbx_token", local_mount_root=self.dropbox_mount)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_buildkite_adapter_and_webhook(self):
        # 1. Trigger Build
        build_info = self.buildkite.trigger_build(
            pipeline="job-app-ci",
            commit_sha="commit_sha_abc123",
            branch="main",
        )
        self.assertEqual(build_info["pipeline"], "job-app-ci")
        self.assertEqual(build_info["status"], "RUNNING")

        # 2. Readback & Verify
        rb = self.buildkite.readback("job-app-ci", build_info["build_number"])
        self.assertTrue(self.buildkite.verify(rb))

        # 3. Webhook Parsing
        webhook_payload = {
            "event": "build.finished",
            "build": {
                "number": build_info["build_number"],
                "commit": "commit_sha_abc123",
                "state": "passed",
                "meta_data": {"mission_id": "msn_001", "correlation_id": "run_001"},
            },
            "pipeline": {"slug": "job-app-ci"},
        }
        event = process_buildkite_event(webhook_payload)
        self.assertEqual(event["state"], "passed")
        self.assertTrue(event["passed"])
        self.assertEqual(event["mission_id"], "msn_001")

    def test_02_notion_cockpit_synchronization(self):
        m = Mission.create(
            objective="Deploy Temporal Cloud",
            project="infrastructure-master",
            priority="P0",
            repositories=["GlacierEQ/monolith"],
        )
        advance_to(m, MissionStatus.EXECUTING)

        # Sync authoritative state to Notion Cockpit
        sync_res = self.notion.sync_mission_state(
            mission=m,
            current_step="Compiling OCI Cloud-Init",
            verified_mutations=3,
            failed_mutations=0,
            receipt_id="rcpt_test_123",
        )
        self.assertEqual(sync_res["status"], "SYNCED")

        # Readback & Verify
        rb = self.notion.readback_page(sync_res["page_id"])
        self.assertTrue(self.notion.verify_update(rb, expected_status=MissionStatus.EXECUTING.value))
        props = rb["properties"]
        self.assertEqual(props["Priority"], "P0")
        self.assertEqual(props["Verified Mutations"], 3)
        self.assertEqual(props["Receipt"], "rcpt_test_123")

    def test_03_dropbox_artifact_provenance(self):
        sample_file = self.test_dir / "court_pleading.pdf"
        sample_file.write_bytes(b"%PDF-1.4 Mock Legal Forensic Pleading Exhibit")
        exp_sha = hashlib.sha256(sample_file.read_bytes()).hexdigest()

        # Upload artifact
        remote_path = "/01_LEGAL/SYNTHESIZED_PLEADINGS/court_pleading.pdf"
        upload_res = self.dropbox.upload_artifact(sample_file, remote_path, mission_id="msn_999")
        self.assertEqual(upload_res["status"], "UPLOADED")
        self.assertEqual(upload_res["content_hash"], exp_sha)

        # Readback & Verify
        rb = self.dropbox.readback(remote_path)
        self.assertTrue(self.dropbox.verify(rb, exp_sha))
        self.assertEqual(rb["size_bytes"], sample_file.stat().st_size)

    def test_04_oci_temporal_provisioner(self):
        spec = OCITemporalProvisioner.generate_launch_spec()
        self.assertEqual(spec["shape"], "VM.Standard.A1.Flex")
        self.assertEqual(spec["shape_config"]["ocpus"], 4)
        self.assertEqual(spec["shape_config"]["memory_in_gbs"], 24)
        self.assertEqual(spec["region"], "mx-monterrey-1")

        # Export deployment packet
        out_d = self.test_dir / "oci_out"
        manifest_file = OCITemporalProvisioner.export_deployment_packet(output_dir=out_d)
        self.assertTrue(manifest_file.exists())
        self.assertTrue((out_d / "launch_instance.sh").exists())


if __name__ == "__main__":
    unittest.main()
