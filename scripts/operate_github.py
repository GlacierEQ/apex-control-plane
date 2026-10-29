#!/usr/bin/env python3
"""Execute one real GitHub file effect and verify via native API readback."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from operational_core import OperationalCore
from provider_github import GitHubContentsAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--id", required=True, help="Stable operation identity")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--path", required=True)
    parser.add_argument("--content-file", type=Path, required=True)
    parser.add_argument("--message", default="APEX verified connector effect")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN must be present in the authorized host environment")
    payload = {"repo": args.repo, "branch": args.branch, "path": args.path,
               "content": args.content_file.read_text(encoding="utf-8"), "message": args.message}
    try:
        with OperationalCore(args.state, {"github.contents": GitHubContentsAdapter(token)}) as core:
            core.submit(args.id, "github.contents", payload)
            status = core.run(args.id)
        print(json.dumps(status.as_dict(), sort_keys=True))
        return 0 if status.verified else 1
    except (KeyError, ValueError, OSError) as error:
        print(json.dumps({"state": "failed", "error": type(error).__name__, "message": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
