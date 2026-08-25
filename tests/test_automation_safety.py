from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "audit_automation_surface.py"
SPEC = importlib.util.spec_from_file_location("audit_automation_surface", MODULE_PATH)
assert SPEC and SPEC.loader
safety = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = safety
SPEC.loader.exec_module(safety)


class AutomationSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, name: str, content: str) -> None:
        (self.root / name).write_text(content, encoding="utf-8")

    def test_read_only_schedule_passes(self) -> None:
        self.write(
            "observe.yml",
            """name: Observe\non:\n  schedule:\n    - cron: '0 * * * *'\npermissions:\n  contents: read\njobs:\n  check:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          persist-credentials: false\n""",
        )
        result = safety.audit(self.root)
        self.assertEqual("PASS", result["status"])
        self.assertEqual(0, result["error_count"])

    def test_scheduled_contents_write_fails(self) -> None:
        self.write(
            "writer.yml",
            """name: Writer\non:\n  schedule:\n    - cron: '0 * * * *'\npermissions:\n  contents: write\njobs:\n  write:\n    steps:\n      - run: echo hi\n""",
        )
        result = safety.audit(self.root)
        codes = {row["code"] for row in result["findings"]}
        self.assertEqual("FAIL", result["status"])
        self.assertIn("SCHEDULED_CONTENTS_WRITE", codes)

    def test_scheduled_static_secret_fails(self) -> None:
        self.write(
            "secret.yml",
            """name: Secret\non:\n  schedule:\n    - cron: '0 * * * *'\njobs:\n  check:\n    steps:\n      - run: echo check\n        env:\n          TOKEN: ${{ secrets.EXTERNAL_TOKEN }}\n""",
        )
        result = safety.audit(self.root)
        codes = {row["code"] for row in result["findings"]}
        self.assertIn("SCHEDULED_STATIC_REPOSITORY_SECRET", codes)

    def test_push_triggered_self_writer_fails(self) -> None:
        self.write(
            "loop.yml",
            """name: Loop\non:\n  push:\n    branches: [main]\npermissions:\n  contents: write\njobs:\n  write:\n    steps:\n      - run: |\n          git commit -am update\n          git push origin HEAD:main\n""",
        )
        result = safety.audit(self.root)
        codes = {row["code"] for row in result["findings"]}
        self.assertIn("PUSH_TRIGGERED_SELF_WRITE", codes)

    def test_manual_write_is_not_inherently_rejected(self) -> None:
        self.write(
            "manual.yml",
            """name: Manual\non:\n  workflow_dispatch:\npermissions:\n  contents: write\njobs:\n  apply:\n    steps:\n      - run: git push origin HEAD:main\n""",
        )
        result = safety.audit(self.root)
        self.assertEqual("PASS", result["status"])

    def test_force_push_is_always_rejected(self) -> None:
        self.write(
            "bad.yml",
            """name: Bad\non:\n  workflow_dispatch:\njobs:\n  bad:\n    steps:\n      - run: git push --force origin main\n""",
        )
        result = safety.audit(self.root)
        codes = {row["code"] for row in result["findings"]}
        self.assertIn("DESTRUCTIVE_GIT_FORCE_PUSH", codes)


if __name__ == "__main__":
    unittest.main()
