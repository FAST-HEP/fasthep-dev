#!/usr/bin/env python3
"""Report which public symbols of each FAST-HEP package no sibling uses, and private names siblings import.

Read-only. It reads the package snapshots in ``DIR/<repo>`` (default ``build/review``, made with
``snapshot.py --dest build/review --execute``), parses every ``*.py`` under each ``src`` and
``tests`` with ``ast`` and matches ``from module import name`` and ``alias.name`` for a module
imported by alias. It does not see names reached by strings (``module:attr`` in YAML) or by
``getattr``, so "unused" is a candidate list, not proof.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

Use = tuple[str, str, str, str]  # (importing repo, "src" or "tests", module, name)


def packages(snapshots: Path) -> dict[str, str]:
    """Map repo name to the importable package under its src."""
    found = {}
    for repo in sorted(p for p in snapshots.iterdir() if (p / "src").is_dir()):
        modules = [m for m in (repo / "src").iterdir() if m.is_dir() and not m.name.startswith((".", "_"))]
        if len(modules) == 1:
            found[repo.name] = modules[0].name
    return found


def dotted(src: Path, path: Path) -> str:
    parts = list(path.relative_to(src).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def public_symbols(src: Path, package: str) -> dict[str, set[str]]:
    """Top-level public functions, classes and variables per module of one package."""
    symbols = {}
    for path in sorted((src / package).rglob("*.py")):
        names = set()
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
        symbols[dotted(src, path)] = {n for n in names if not n.startswith("_")}
    return symbols


def uses_in(path: Path, modules: set[str]) -> set[tuple[str, str]]:
    """(module, name) pairs of the known modules that one file imports or reaches by alias."""
    uses = set()
    aliases = {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for item in node.names:
                if f"{node.module}.{item.name}" in modules:
                    aliases[item.asname or item.name] = f"{node.module}.{item.name}"
                elif node.module in modules:
                    uses.add((node.module, item.name))
        elif isinstance(node, ast.Import):
            for item in node.names:
                if item.asname and item.name in modules:
                    aliases[item.asname] = item.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            uses.add((aliases[node.value.id], node.attr))
    return uses


def survey(snapshots: Path) -> tuple[dict[str, dict[str, set[str]]], list[Use]]:
    owners = packages(snapshots)
    defined = {repo: public_symbols(snapshots / repo / "src", module) for repo, module in owners.items()}
    modules = {m for symbols in defined.values() for m in symbols}
    owner_of = {m: repo for repo, symbols in defined.items() for m in symbols}
    uses = []
    for repo in owners:
        for tree in ("src", "tests"):
            for path in sorted((snapshots / repo / tree).rglob("*.py")):
                for module, name in sorted(uses_in(path, modules)):
                    if owner_of[module] != repo:
                        uses.append((repo, tree, module, name))
    return defined, uses


def report(snapshots: Path, only: set[str]) -> tuple[list[str], int]:
    defined, uses = survey(snapshots)
    used = defaultdict(set)
    for _, _, module, name in uses:
        used[module].add(name)
    lines, private = [], 0
    for repo, symbols in defined.items():
        if only and repo not in only:
            continue
        unused = {m: sorted(n - used[m]) for m, n in symbols.items() if n - used[m]}
        total = sum(len(n) for n in symbols.values())
        lines.append(f"## {repo}: {sum(map(len, unused.values()))} of {total} public symbols have no sibling user")
        lines += [f"  {module}: {', '.join(names)}" for module, names in unused.items()]
        theirs = sorted({u for u in uses if u[2] in symbols and u[3].startswith("_") and not u[3].startswith("__")})
        private += len(theirs)
        lines.append(f"## {repo}: {len(theirs)} private names imported by siblings")
        lines += [f"  {importer} ({tree}) -> {module}.{name}" for importer, tree, module, name in theirs]
    return lines, private


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="workspace root (default: cwd)")
    parser.add_argument("--dest", type=Path, default=Path("build/review"), help="snapshot directory (default: build/review)")
    parser.add_argument("--repo", action="append", default=[], help="report only this package (repeatable)")
    parser.add_argument("--fail-on-private", action="store_true", help="exit 1 if a sibling imports a private name")
    args = parser.parse_args(argv)
    snapshots = (args.root.resolve() / args.dest).resolve()
    if not snapshots.is_dir():
        print(f"no snapshots in {snapshots}; run snapshot.py --dest {args.dest} --execute", file=sys.stderr)
        return 2
    lines, private = report(snapshots, set(args.repo))
    print("\n".join(lines))
    return int(args.fail_on_private and private > 0)


if __name__ == "__main__":
    raise SystemExit(main())
