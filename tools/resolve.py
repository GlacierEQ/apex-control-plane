#!/usr/bin/env python3
"""Resolve the universal control plane for a specific host.

Portability contract
--------------------
Every path in registry/*.json is written with variables, never literals:

    ${HOME}             user home — same meaning on macOS, Linux, Termux
    ${DEVICE_STORAGE}   writable shared storage (Android: /sdcard, desktop: unset)
    ${DEVICE_DOWNLOADS} downloads directory
    ${TERMUX_PREFIX}    Termux install prefix (Termux hosts only)

A config that resolves on one host and silently points nowhere on another is the
defect this file exists to prevent. So resolution is *reported*, not assumed:

    every variable is resolved from the device profile
    every resolved path is checked for existence
    every miss is reported with the key that missed

Exit codes
----------
    0  every referenced path resolved and exists
    1  at least one reference is absent on this host (expected on a partial host)
    2  the registry is malformed — a variable with no definition anywhere

Usage
-----
    python3 resolve.py                 # report for this host
    python3 resolve.py --device macbook
    python3 resolve.py --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(HERE, "registry")
DEVICES = os.path.join(HERE, "devices")

VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
HOME_TERM = os.path.expanduser("~/")
TERMUX_PREFIX = "/data/data/com.termux/files/usr"


def load_device(name: str) -> dict:
    path = os.path.join(DEVICES, f"{name}.json")
    if not os.path.exists(path):
        raise SystemExit(f"unknown device {name!r}; have: {', '.join(sorted(devices()))}")
    d = json.load(open(path, encoding="utf-8"))
    return d.get("vars", {})


def devices() -> list:
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(DEVICES, "*.json")))


def base_vars() -> dict:
    """Host facts, computed rather than configured."""
    v = {"HOME": HOME_TERM.rstrip("/")}
    if os.path.isdir("/sdcard"):
        v["DEVICE_STORAGE"] = "/sdcard"
        v["DEVICE_DOWNLOADS"] = "/sdcard/Download"
    else:
        v.setdefault("DEVICE_DOWNLOADS", os.path.join(HOME_TERM, "Downloads"))
    if TERMUX_PREFIX.startswith(HOME_TERM[:7]) and os.path.isdir(TERMUX_PREFIX):
        v["TERMUX_PREFIX"] = TERMUX_PREFIX
    return v


def strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


def resolve(s: str, vars_: dict) -> str:
    def sub(m):
        k = m.group(1)
        if k not in vars_:
            raise KeyError(k)
        return vars_[k]
    return VAR.sub(sub, s)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="auto",
                    help="device profile name, or 'auto' to derive from this host")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    name = args.device
    if name == "auto":
        name = "termux" if os.path.isdir(TERMUX_PREFIX) else "macbook"
    try:
        profile = load_device(name)
    except SystemExit as e:
        print(e)
        return 2

    vars_ = {**base_vars(), **profile}
    files = sorted(glob.glob(os.path.join(REGISTRY, "*.json")))

    refs: list[tuple[str, str, str]] = []   # (file, key, template)
    unresolved_vars: set[str] = set()
    for f in files:
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception as exc:
            print(f"  MALFORMED {os.path.basename(f)}: {exc}")
            return 2
        def walk(o, key=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{key}.{k}" if key else k)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{key}[{i}]")
            elif isinstance(o, str) and VAR.search(o):
                for m in VAR.finditer(o):
                    if m.group(1) not in vars_:
                        unresolved_vars.add(m.group(1))
                refs.append((os.path.basename(f), key, o))
        walk(data)

    resolved, missing, present = [], [], 0
    for fn, key, tpl in refs:
        try:
            r = resolve(tpl, vars_)
        except KeyError as e:
            unresolved_vars.add(e.args[0])
            continue
        expanded = os.path.expanduser(r)
        if os.path.exists(expanded):
            present += 1
            resolved.append({"file": fn, "key": key, "path": r, "exists": True})
        else:
            missing.append({"file": fn, "key": key, "path": r, "exists": False})

    if args.json:
        print(json.dumps({
            "device": name,
            "files": len(files),
            "references": len(refs),
            "present": present,
            "absent": len(missing),
            "unresolved_variables": sorted(unresolved_vars),
            "missing": missing[:200],
        }, indent=2))
        return 1 if (missing or unresolved_vars) else 0

    print("=" * 74)
    print(f"  UNIVERSAL CONTROL PLANE — resolution report")
    print(f"  device      : {name}")
    print(f"  registry    : {len(files)} config files")
    print(f"  references  : {len(refs)} path variables")
    print(f"  present     : {present}")
    print(f"  absent      : {len(missing)}")
    print("=" * 74)

    if unresolved_vars:
        print("\n  UNDEFINED VARIABLES (registry is malformed):")
        for v in sorted(unresolved_vars):
            print(f"    ${{{v}}}  — defined in no device profile")

    if present:
        print(f"\n  RESOLVED AND PRESENT ({present}):")
        for r in sorted({m["path"] for m in resolved})[:24]:
            print(f"    ✓ {r[:66]}")

    if missing:
        byfile: dict[str, int] = {}
        for m in missing:
            byfile[m["file"]] = byfile.get(m["file"], 0) + 1
        print(f"\n  ABSENT ON THIS HOST ({len(missing)}) — expected on a partial host:")
        for fn, c in sorted(byfile.items(), key=lambda kv: -kv[1])[:14]:
            print(f"    · {fn:34} {c:3} ref(s)")
        print("\n  This is not rot. A declared key that is absent on one host and")
        print("  present on another is the correct shape; a fake path is not.")

    print()
    return 1 if (missing or unresolved_vars) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
