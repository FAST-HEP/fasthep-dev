#!/usr/bin/env python3
"""Cross-package checks over the package snapshots in ``DIR/<repo>`` (default ``build/review``).

Read-only. Subcommands: ``duplicates`` (private functions defined in more than one repository, with
identical bodies marked), ``strings`` (``module:attr`` strings that cross repositories or point at a
name that does not exist), ``floors`` (``requires-python`` and sibling dependency floors per repository)
and ``stale`` (is the newest review of a repository out of date; see docs/review-format.md).
Private imports and unused public symbols are in ``api_surface.py``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections import defaultdict
from datetime import date
from pathlib import Path

from scripts.dev.api_surface import dotted, packages
from scripts.dev.snapshot import git

MAX_AGE_DAYS = 30
MAX_COMMITS_BEHIND = 20
REFERENCE = re.compile(r"\b([A-Za-z_][\w.]*):([A-Za-z_]\w*)\b")


def private_functions(src: Path, package: str) -> dict[str, list[tuple[str, str]]]:
    """name -> [(file, body fingerprint)] for module-level ``_name`` functions of one package."""
    found = defaultdict(list)
    for path in sorted((src / package).rglob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("_") and not node.name.startswith("__"):
                body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
                found[node.name].append((str(path.relative_to(src.parent)), body))
    return found


def duplicates(snapshots: Path) -> list[dict]:
    homes = defaultdict(dict)
    for repo, package in packages(snapshots).items():
        for name, places in private_functions(snapshots / repo / "src", package).items():
            homes[name][repo] = places
    result = []
    for name, repos in sorted(homes.items()):
        if len(repos) < 2:
            continue
        bodies = {body for places in repos.values() for _, body in places}
        result.append({
            "name": name,
            "identical": len(bodies) == 1,
            "where": {repo: [f for f, _ in places] for repo, places in repos.items()},
        })
    return result


def strings(snapshots: Path) -> list[dict]:
    owners = packages(snapshots)
    owner_of, text = {}, {}
    for repo, package in owners.items():
        src = snapshots / repo / "src"
        for path in (src / package).rglob("*.py"):
            owner_of[dotted(src, path)] = repo
            text[dotted(src, path)] = path.read_text(encoding="utf-8")
    result = []
    for repo in owners:
        for path in sorted((snapshots / repo / "src").rglob("*")):
            if path.suffix not in {".yaml", ".yml", ".toml", ".py"}:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for module, attr in REFERENCE.findall(line):
                    if module not in owner_of:
                        continue
                    missing = f"{module}.{attr}" not in owner_of and not re.search(rf"\b{attr}\b", text[module])
                    if owner_of[module] != repo or missing:
                        result.append({
                            "from": repo, "file": str(path.relative_to(snapshots / repo)), "line": number,
                            "target": f"{module}:{attr}", "crosses": owner_of[module] != repo, "missing": missing,
                        })
    return result


def floors(snapshots: Path) -> dict[str, dict]:
    owners = set(packages(snapshots))
    names = {repo: (snapshots / repo / "pyproject.toml") for repo in owners}
    result = {}
    for repo, path in names.items():
        if not path.is_file():
            continue
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
        deps = {}
        for spec in project.get("dependencies", []):
            name = re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].lower().replace("_", "-")
            if name.startswith("fasthep"):
                deps[name] = spec
        result[repo] = {"requires-python": project.get("requires-python", ""), "siblings": deps}
    return result


def stale(reports: Path, snapshots: Path, repo: str, today: date | None = None) -> tuple[bool, list[str]]:
    """(is stale, reasons) for the newest review of ``repo``; a missing review is stale."""
    runs = sorted((reports / repo).glob("*/findings.json"))
    if not runs:
        return True, ["no review yet"]
    data = json.loads(runs[-1].read_text(encoding="utf-8"))
    head = git(snapshots / repo, "rev-parse", "HEAD")
    reasons = []
    age = ((today or date.today()) - date.fromisoformat(data["date"])).days
    if age > MAX_AGE_DAYS:
        reasons.append(f"{age} days old (limit {MAX_AGE_DAYS})")
    if head == data["commit"]:
        return bool(reasons), reasons
    behind = int(git(snapshots / repo, "rev-list", "--count", f"{data['commit']}..{head}") or 0)
    if behind > MAX_COMMITS_BEHIND:
        reasons.append(f"{behind} commits behind (limit {MAX_COMMITS_BEHIND})")
    scope = runs[-1].with_name("scope.txt")
    reviewed = {line.split()[0] for line in scope.read_text(encoding="utf-8").splitlines() if line.strip()} if scope.is_file() else set()
    changed = set(git(snapshots / repo, "diff", "--name-only", f"{data['commit']}..{head}").splitlines()) & reviewed
    if changed:
        reasons.append(f"{len(changed)} reviewed files changed")
    return bool(reasons), reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=["duplicates", "strings", "floors", "stale"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dest", type=Path, default=Path("build/review"))
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--repo", action="append", default=[], help="stale: repository to check (repeatable; default all)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    snapshots = (root / args.dest).resolve()
    if not snapshots.is_dir():
        print(f"no snapshots in {snapshots}; run snapshot.py --dest {args.dest} --execute", file=sys.stderr)
        return 2
    if args.check == "stale":
        status = 0
        for repo in args.repo or sorted(packages(snapshots)):
            is_stale, reasons = stale(root / args.reports, snapshots, repo)
            print(f"{repo}: {'STALE: ' + '; '.join(reasons) if is_stale else 'current'}")
            status |= int(is_stale)
        return status
    print(json.dumps({"duplicates": duplicates, "strings": strings, "floors": floors}[args.check](snapshots), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
