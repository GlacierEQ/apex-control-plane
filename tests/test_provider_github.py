"""Provider adapter behavior using an in-process GitHub API double."""
import base64
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from operational_core import OperationalCore
from provider_github import GitHubContentsAdapter


class FakeGithub(GitHubContentsAdapter):
    def __init__(self):
        super().__init__("test-token")
        self.data = {}
        self.writes = 0
        self.calls = []
        self.fail_reads = False

    def _request(self, method, url, body=None):
        self.calls.append((method, url))
        if method == "GET":
            if self.fail_reads:
                raise OSError("GitHub unavailable")
            path = url.split("/contents/")[1].split("?")[0]
            if path not in self.data:
                raise HTTPError(url, 404, "Not Found", {}, None)
            value = self.data[path]
            return {"type": "file", "encoding": "base64",
                    "content": base64.b64encode(value).decode(), "sha": "existing-sha"}
        if method == "PUT":
            path = url.split("/contents/")[1]
            self.writes += 1
            self.data[path] = base64.b64decode(body["content"])
            return {"commit": {"sha": "remote-commit"}}
        raise AssertionError(method)


class GithubTests(unittest.TestCase):
    def setUp(self):
        self.remote = FakeGithub()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.core = OperationalCore(Path(self.tmp.name) / "state.sqlite", {"github": self.remote})
        self.addCleanup(self.core.close)
        self.payload = {"repo": "GlacierEQ/apex-control-plane", "branch": "main",
                        "path": "proof/result.txt", "content": "operating"}

    def test_actual_native_write_then_independent_get(self):
        self.core.submit("github-proof", "github", self.payload)
        self.assertTrue(self.core.run("github-proof").verified)
        self.assertEqual(self.remote.data["proof/result.txt"], b"operating")
        self.assertEqual(self.remote.writes, 1)
        self.assertEqual([x[0] for x in self.remote.calls], ["GET", "PUT", "GET"])
        self.assertTrue(self.core.run("github-proof").verified)
        self.assertEqual(self.remote.writes, 1)

    def test_existing_content_rewritten_and_verified(self):
        self.remote.data["proof/result.txt"] = b"old"
        self.core.submit("update", "github", self.payload)
        self.assertTrue(self.core.run("update").verified)
        self.assertEqual(self.remote.writes, 1)

    def test_lost_readback_never_claims_success_or_repeats(self):
        self.remote.fail_reads = True
        self.core.submit("readback", "github", self.payload)
        self.assertEqual(self.core.run("readback").state, "uncertain")
        self.assertEqual(self.remote.writes, 0)
        self.remote.fail_reads = False
        self.assertTrue(self.core.run("readback").verified)
        self.assertEqual(self.remote.writes, 1)

    def test_invalid_path_refused(self):
        payload = dict(self.payload, path="../outside")
        self.core.submit("bad", "github", payload)
        self.assertFalse(self.core.run("bad").verified)
        self.assertEqual(self.remote.writes, 0)

    def test_token_required(self):
        with self.assertRaises(ValueError):
            GitHubContentsAdapter("")


if __name__ == "__main__":
    unittest.main()
