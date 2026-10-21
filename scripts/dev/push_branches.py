#!/usr/bin/env python3
"""Push the branches of a stacked PR set listed in a manifest (a human gate).

Default is a dry run: for every entry it shows the local and remote tip, whether the
push would create the branch or fast-forward it, and the exact command. ``--execute``
pushes, after a typed confirmation on a terminal; without a terminal it refuses, so an
agent or a pipeline cannot push for you. It never forces, never deletes, and skips a
branch whose remote has diverged.

Manifest (YAML), repository paths relative to ``--root``::

    branches:
      - {repo: flow, branch: feat/shared-prefix-output-delivery}
      - {repo: distributed, branch: feat/shared-prefix-and-output-delivery}
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


@dataclass
class Item:
    repo: Path
    name: str
    branch: str
    local: str = ""
    remote: str = ""
    state: str = ""
    pushable: bool = False


def inspect(item: Item) -> Item:
    local = git(item.repo, "rev-parse", "--verify", "-q", f"refs/heads/{item.branch}", check=False)
    if local.returncode != 0:
        item.state = "MISSING locally"
        return item
    item.local = local.stdout.strip()
    ls = git(item.repo, "ls-remote", "--heads", "origin", item.branch, check=False)
    if ls.returncode != 0:
        item.state = f"remote unreachable: {ls.stderr.strip().splitlines()[-1] if ls.stderr.strip() else 'error'}"
        return item
    item.remote = ls.stdout.split("\t")[0].strip() if ls.stdout.strip() else ""
    if not item.remote:
        item.state, item.pushable = "new branch", True
    elif item.remote == item.local:
        item.state = "up to date"
    elif git(item.repo, "cat-file", "-e", f"{item.remote}^{{commit}}", check=False).returncode != 0:
        item.state = "DIVERGED? remote tip not in local history (fetch first); not pushed"
    elif git(item.repo, "merge-base", "--is-ancestor", item.remote, item.local, check=False).returncode == 0:
        ahead = git(item.repo, "rev-list", "--count", f"{item.remote}..{item.local}").stdout.strip()
        item.state, item.pushable = f"fast-forward (+{ahead} commits)", True
    else:
        item.state = "DIVERGED; would need a force push; not pushed"
    return item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="workspace root (default: cwd)")
    parser.add_argument("--manifest", type=Path, default=Path("tasks/push-manifest.yaml"))
    parser.add_argument("--execute", action="store_true", help="push (default: dry run)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
    entries = (yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}).get("branches") or []
    items = [inspect(Item(root / e["repo"], e["repo"], e["branch"])) for e in entries]

    print(f"{'repo':<18} {'branch':<46} {'local':<8} {'remote':<8} state")
    for item in items:
        print(f"{item.name:<18} {item.branch:<46} {item.local[:7]:<8} {item.remote[:7]:<8} {item.state}")
    todo = [i for i in items if i.pushable]
    print(f"\n{len(todo)} of {len(items)} branches would be pushed:")
    for item in todo:
        print(f"  git -C {item.name} push -u origin {item.branch}")
    if not args.execute:
        print("Dry run: nothing pushed. Add --execute to push (needs a terminal).")
        return 0
    if not todo:
        print("Nothing to push.")
        return 0
    if not sys.stdin.isatty():
        print("Refusing: no terminal to confirm on (the push is a human gate).", file=sys.stderr)
        return 2
    if input(f"Type 'push' to push {len(todo)} branches: ").strip() != "push":
        print("Aborted.")
        return 1
    failed = 0
    for item in todo:
        print(f"== {item.name} {item.branch}")
        result = subprocess.run(["git", "-C", str(item.repo), "push", "-u", "origin", item.branch], check=False)
        failed += result.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
