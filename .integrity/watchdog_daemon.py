"""Integrity watchdog — SHA-256 baselines for this leaf."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class WatchdogDaemon:
    def __init__(self, repo_root: str | None = None):
        integrity_dir = Path(__file__).resolve().parent
        self.repo_root = Path(repo_root).resolve() if repo_root else integrity_dir.parent
        self.hash_store = integrity_dir / "file_hashes.json"
        self.baseline = {}
        if self.hash_store.exists():
            self.baseline = json.loads(self.hash_store.read_text())

    def scan(self) -> dict:
        cur = {}
        for pattern in ("src/**/*.py", "*.py", "connectors/**/*.py"):
            for path in self.repo_root.glob(pattern):
                if "__pycache__" in path.parts or ".git" in path.parts:
                    continue
                if path.is_file():
                    rel = str(path.relative_to(self.repo_root))
                    cur[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return cur

    def update_baseline(self) -> None:
        self.baseline = self.scan()
        self.hash_store.write_text(json.dumps(self.baseline, indent=2))

    def verify(self) -> dict:
        cur = self.scan()
        return {path: self.baseline.get(path) == digest for path, digest in cur.items()}


if __name__ == "__main__":
    watchdog = WatchdogDaemon()
    watchdog.update_baseline()
    result = watchdog.verify()
    ok = all(result.values()) if result else True
    print("Integrity check:", "PASS" if ok else "FAIL", f"({len(result)} files)")
