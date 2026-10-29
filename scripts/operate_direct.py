#!/usr/bin/env python3
"""Execute explicitly requested local effects without legacy startup gates."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from operational_core import FileWriteAdapter, OperationalCore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True, help="Durable SQLite journal")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Trusted workspace root for file effects (default: current directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit-file", help="Submit and immediately execute a file action")
    submit.add_argument("--id", required=True, help="Stable idempotency key")
    submit.add_argument("--path", required=True, type=Path)
    submit.add_argument("--queue-only", action="store_true", help="Persist without executing")
    group = submit.add_mutually_exclusive_group(required=True)
    group.add_argument("--content")
    group.add_argument("--content-file", type=Path)
    run = commands.add_parser("run", help="Execute/reconcile one queued operation")
    run.add_argument("--id", required=True)
    status = commands.add_parser("status", help="Inspect state without claiming execution")
    status.add_argument("--id", required=True)
    args = parser.parse_args()
    try:
        with OperationalCore(args.state, {"file.write": FileWriteAdapter(args.root)}) as core:
            if args.command == "submit-file":
                content = args.content if args.content is not None else args.content_file.read_text(encoding="utf-8")
                result = core.submit(args.id, "file.write", {"path": str(args.path), "content": content})
                if not args.queue_only:
                    result = core.run(args.id)
            elif args.command == "run":
                result = core.run(args.id)
            else:
                result = core.status(args.id)
        print(json.dumps(result.as_dict(), sort_keys=True))
        return 0 if result.verified or (args.command == "submit-file" and args.queue_only) or args.command == "status" else 1
    except (KeyError, ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "reason": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
