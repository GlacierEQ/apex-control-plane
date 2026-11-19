"""Tool catalog: the whole inventory, visible; loading is a per-turn choice.

The catalog keeps every skill and connector the engine can reach in one
visible list. Nothing is hidden, nothing is capped. What gets loaded for
a turn is the caller's per-turn choice, and the choice can change next
turn (hot swap). The loaded set is small; what can be accessed is
everything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class CatalogEntry:
    """One thing the engine can reach: a skill or a connector."""

    name: str
    kind: str  # "skill" or "connector"
    description: str
    path: str


def _describe_doc(path: Path) -> str:
    """First bullet line of a SKILL.md / CONNECTOR.md, truncated."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("- "):
                return line[2:].strip()[:160]
    except OSError:
        return ""
    return ""


def build_catalog(
    skill_dirs: Sequence[str | Path], connector_dirs: Sequence[str | Path]
) -> list[CatalogEntry]:
    """Enumerate every skill and connector into one catalog.

    The catalog is complete: every entry found on disk is listed, none
    hidden, none capped. Knowing what can be accessed is the catalog's
    job; deciding what to load for a turn is the caller's.
    """
    entries: list[CatalogEntry] = []
    seen_docs: set[tuple[str, Path]] = set()
    for kind, dirs, fname in (
        ("skill", skill_dirs, "SKILL.md"),
        ("connector", connector_dirs, "CONNECTOR.md"),
    ):
        for base in dirs:
            base = Path(base)
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir(), key=lambda p: p.name):
                doc = child / fname
                if child.is_dir() and doc.is_file():
                    # Overlapping roots and aliases must not manufacture ambiguity.
                    identity = (kind, doc.resolve())
                    if identity in seen_docs:
                        continue
                    seen_docs.add(identity)
                    entries.append(
                        CatalogEntry(
                            name=child.name,
                            kind=kind,
                            description=_describe_doc(doc),
                            path=str(doc),
                        )
                    )
    return entries


def menu(catalog: Sequence[CatalogEntry]) -> list[str]:
    """The whole catalog as one line per entry. Visible, nothing loaded."""
    return [f"{e.kind}: {e.name} — {e.description}" for e in catalog]


def search_catalog(catalog: Sequence[CatalogEntry], query: str) -> list[CatalogEntry]:
    """Every match, no cap. The caller sees all candidates and picks."""
    words = {w.lower() for w in query.split() if w}
    if not words:
        return []
    return [
        e
        for e in catalog
        if any(w in f"{e.name} {e.description}".lower() for w in words)
    ]


def select(catalog: Sequence[CatalogEntry], wanted: Sequence[str]) -> list[CatalogEntry]:
    """Per-turn selection by explicit name. No fixed k, no ranker guessing.

    A name that matches nothing returns nothing: refuse-to-guess applies.
    Ambiguous names raise ValueError; use kind:name to disambiguate.
    """
    by_name: dict[str, list[CatalogEntry]] = {}
    by_qualified: dict[str, list[CatalogEntry]] = {}
    for entry in catalog:
        by_name.setdefault(entry.name, []).append(entry)
        by_qualified.setdefault(f"{entry.kind}:{entry.name}", []).append(entry)

    selected: list[CatalogEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for name in wanted:
        # A literal capability name may contain ":". Resolve both namespaces and
        # reject collisions rather than silently preferring either one.
        candidates = by_name.get(name, []) + by_qualified.get(name, [])
        matches = list({id(entry): entry for entry in candidates}.values())
        if len(matches) > 1:
            raise ValueError(
                f"ambiguous catalog selection {name!r}; specify a unique kind:name"
            )
        if matches:
            entry = matches[0]
            identity = (entry.kind, entry.name, entry.path)
            if identity not in seen:
                selected.append(entry)
                seen.add(identity)
    return selected


def hot_swap(
    _loaded: Sequence[CatalogEntry],
    catalog: Sequence[CatalogEntry],
    wanted: Sequence[str],
) -> list[CatalogEntry]:
    """Replace the loaded set with a new selection.

    The old set drops back to the menu: still in the catalog, still
    reachable, never walled off. The loaded set is a per-turn choice,
    not a ceiling on what can be accessed.
    """
    return select(catalog, wanted)


def main(argv: Sequence[str] | None = None) -> int:
    """Operator-invocable discovery and selection boundary; never executes tools.

    Prints deterministic JSON for a downstream loader. A requested capability
    must resolve exactly once: missing or ambiguous selections fail closed.
    """
    parser = argparse.ArgumentParser(description="Discover and resolve agent capabilities")
    parser.add_argument("--skills", action="append", default=[], metavar="DIR")
    parser.add_argument("--connectors", action="append", default=[], metavar="DIR")
    parser.add_argument("--select", action="append", default=[], metavar="KIND:NAME")
    parser.add_argument("--load-content", action="store_true", help="Read selected capability documents into JSON")
    parser.add_argument("--expect-sha256", action="append", default=[], metavar="DIGEST", help="Require each selected document to match its expected SHA-256 (in selection order)")
    args = parser.parse_args(argv)
    if args.expect_sha256 and (not args.load_content or len(args.expect_sha256) != len(args.select)):
        print("--expect-sha256 requires --load-content and one digest per --select", file=sys.stderr)
        return 2
    if any(len(d) != 64 or any(c not in "0123456789abcdef" for c in d) for d in args.expect_sha256):
        print("expected SHA-256 must be 64 lowercase hexadecimal characters", file=sys.stderr)
        return 2
    if args.load_content and not args.select:
        print("--load-content requires at least one explicit --select", file=sys.stderr)
        return 2
    catalog = build_catalog(args.skills, args.connectors)
    try:
        chosen = select(catalog, args.select) if args.select else catalog
        if args.select:
            resolved = {e.name for e in chosen} | {f"{e.kind}:{e.name}" for e in chosen}
            missing = [name for name in args.select if name not in resolved]
            if missing:
                raise ValueError(f"unknown catalog selection: {missing!r}")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = []
    try:
        for entry in chosen:
            record = asdict(entry)
            if args.load_content:
                # Resolve all requested documents before emitting any output.
                # Never return a partially loaded capability set.
                content = Path(entry.path).read_bytes()
                record["content"] = content.decode("utf-8")
                record["sha256"] = hashlib.sha256(content).hexdigest()
                if args.expect_sha256:
                    requested = [name for name in args.select if name == entry.name or name == f"{entry.kind}:{entry.name}"]
                    expected = {args.expect_sha256[i] for i, name in enumerate(args.select) if name in requested}
                    if expected != {record["sha256"]}:
                        raise ValueError(f"capability document digest mismatch: {entry.kind}:{entry.name}")
            output.append(record)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"cannot load capability document: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
