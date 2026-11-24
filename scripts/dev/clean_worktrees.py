#!/usr/bin/env python3
"""List and, on request, remove the git worktrees under ``build/worktrees/``.

Each worktree is compared with its upstream and with the default branch of ``origin``:

* ``merged``: HEAD is contained in ``origin/<default>``;
* ``pushed``: HEAD is contained in some remote branch;
* ``dirty``: tracked changes or untracked (not ignored) files;
* ``ignored``: files git ignores (build output, caches); ``git worktree remove`` deletes them too.

The default is a read-only list (after ``git fetch``; ``--no-fetch`` skips it). ``--execute`` asks
``delete? [y/N]`` for each worktree, showing the details first. A worktree that is dirty or not
pushed needs its full name typed instead of ``y``. This is a human gate: it needs a terminal, is
refused without one, and has no option to skip it (an agent or a pipeline cannot confirm for you).
Removal is ``git worktree remove`` (never ``--force`` unless you typed the name of a dirty tree),
so the branch itself is kept; delete it separately once it is merged.

Every git call sets ``GIT_WORK_TREE`` to the worktree: submodule worktrees whose shared config has
``core.worktree`` fail with ``cannot chdir`` otherwise (see AGENTS.md).

FAST-HEP only: ``hinv/`` is not touched.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

WORKTREE_DIR = Path("build") / "worktrees"
IGNORED_PREVIEW = 5


def git(path: Path, *args: str, check: bool = True) -> str:
    """Run git in the worktree ``path``; return stdout."""
    env = {**os.environ, "GIT_WORK_TREE": str(path)}
    done = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, env=env, check=False
    )
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {path}: {done.stderr.strip()}")
    return done.stdout


def git_ok(path: Path, *args: str) -> bool:
    env = {**os.environ, "GIT_WORK_TREE": str(path)}
    return (
        subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, env=env, check=False
        ).returncode
        == 0
    )


@dataclass
class Worktree:
    path: Path
    branch: str | None = None
    head: str = ""
    upstream: str | None = None
    ahead: int = 0
    merged: bool = False
    pushed: bool = False
    dirty: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def needs_typed_name(self) -> bool:
        return bool(self.dirty) or not self.pushed

    def verdict(self) -> str:
        if self.error:
            return f"ERROR: {self.error}"
        if self.dirty:
            return "DIRTY"
        if not self.pushed:
            return "UNPUSHED"
        return "merged" if self.merged else "pushed, not merged"


def find_worktrees(root: Path) -> list[Path]:
    base = root / WORKTREE_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / ".git").exists())


def default_branch(path: Path) -> str:
    ref = git(path, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False).strip()
    if ref:
        return ref.removeprefix("refs/remotes/")
    return "origin/main"


def inspect(path: Path, *, fetch: bool) -> Worktree:
    wt = Worktree(path)
    try:
        if fetch:
            git(path, "fetch", "--quiet", "origin", check=False)
        wt.head = git(path, "rev-parse", "--short", "HEAD").strip()
        branch = git(path, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
        wt.branch = branch or None
        upstream = git(
            path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False
        ).strip()
        wt.upstream = upstream or None
        if wt.upstream:
            count = git(path, "rev-list", "--count", f"{wt.upstream}..HEAD", check=False).strip()
            wt.ahead = int(count or 0)
        wt.pushed = bool(git(path, "branch", "-r", "--contains", "HEAD", check=False).strip())
        wt.merged = git_ok(path, "merge-base", "--is-ancestor", "HEAD", default_branch(path))
        for line in git(path, "status", "--porcelain", "--ignored").splitlines():
            (wt.ignored if line.startswith("!!") else wt.dirty).append(line[3:])
    except (RuntimeError, ValueError) as error:
        wt.error = str(error)
    return wt


def describe(wt: Worktree) -> str:
    where = wt.branch or "(detached)"
    up = wt.upstream or "no upstream"
    ahead = f", {wt.ahead} ahead" if wt.ahead else ""
    return (
        f"{wt.name:<48} {where:<40} {wt.head:<8} {up}{ahead}; "
        f"{len(wt.dirty)} dirty, {len(wt.ignored)} ignored; {wt.verdict()}"
    )


COLUMNS = ("WORKTREE", "BRANCH", "HEAD", "UPSTREAM", "AHEAD", "DIRTY", "IGNORED", "STATE")
LEGEND = """\
Columns:
  WORKTREE  folder under build/worktrees
  BRANCH    checked-out branch, or (detached)
  HEAD      short commit id
  UPSTREAM  branch the local branch tracks (origin/main for most new worktrees), or none
  AHEAD     commits on HEAD that the upstream does not have
  DIRTY     tracked changes plus untracked files that are not ignored
  IGNORED   ignored files and folders (build output, caches); deleted with the worktree
States:
  merged              HEAD is in origin/<default branch>: safe to remove
  pushed, not merged  HEAD is on a remote branch but not yet in the default branch
  UNPUSHED            HEAD is on no remote: removing loses commits (the branch ref is kept)
  DIRTY               uncommitted work: removing loses it"""


def row(wt: Worktree) -> tuple[str, ...]:
    return (
        wt.name,
        wt.branch or "(detached)",
        wt.head,
        wt.upstream or "none",
        str(wt.ahead),
        str(len(wt.dirty)),
        str(len(wt.ignored)),
        wt.verdict(),
    )


def table(worktrees: list[Worktree]) -> str:
    rows = [COLUMNS, *(row(w) for w in worktrees)]
    widths = [max(len(r[i]) for r in rows) for i in range(len(COLUMNS))]
    numeric = {COLUMNS.index(c) for c in ("AHEAD", "DIRTY", "IGNORED")}
    lines = []
    for n, r in enumerate(rows):
        cells = [c.rjust(widths[i]) if i in numeric else c.ljust(widths[i]) for i, c in enumerate(r)]
        lines.append("  ".join(cells).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def confirm(wt: Worktree, ask=input) -> bool:
    print()
    print(describe(wt))
    for item in wt.dirty[:IGNORED_PREVIEW]:
        print(f"    dirty:   {item}")
    for item in wt.ignored[:IGNORED_PREVIEW]:
        print(f"    ignored: {item}")
    hidden = max(len(wt.ignored) - IGNORED_PREVIEW, 0)
    if hidden:
        print(f"    ... and {hidden} more ignored (deleted with the worktree)")
    if wt.needs_typed_name:
        reason = "has uncommitted changes" if wt.dirty else "has commits that are on no remote"
        return ask(f"  {wt.name} {reason}. Type its name to delete, anything else keeps it: ").strip() == wt.name
    return ask(f"  delete {wt.name}? [y/N] ").strip().lower() == "y"


def remove(wt: Worktree) -> bool:
    args = ["worktree", "remove"]
    if wt.dirty:
        args.append("--force")
    common = git(wt.path, "rev-parse", "--git-common-dir").strip()
    common_path = Path(common) if os.path.isabs(common) else (wt.path / common)
    env = {**os.environ, "GIT_WORK_TREE": str(wt.path)}
    done = subprocess.run(
        ["git", "--git-dir", str(common_path.resolve()), *args, str(wt.path)],
        capture_output=True, text=True, env=env, check=False,
    )
    if done.returncode != 0:
        print(f"  not removed: {done.stderr.strip()}", file=sys.stderr)
        print(f"  by hand: git --git-dir {common_path.resolve()} {' '.join(args)} {wt.path}", file=sys.stderr)
        return False
    print(f"  removed {wt.name} (branch {wt.branch or 'none'} kept)")
    return True


def main(argv: list[str] | None = None, ask=input) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="workspace root (default: cwd)")
    parser.add_argument("--only", action="append", metavar="GLOB", help="only worktrees whose name matches GLOB")
    parser.add_argument("--merged-only", action="store_true", help="only worktrees whose HEAD is in the default branch")
    parser.add_argument("--no-fetch", action="store_true", help="do not run git fetch first")
    parser.add_argument("--execute", action="store_true", help="ask per worktree and remove (default: list only)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    found = [inspect(p, fetch=not args.no_fetch) for p in find_worktrees(root)]
    shown = [
        w for w in found
        if (not args.only or any(fnmatch.fnmatch(w.name, g) for g in args.only))
        and (not args.merged_only or w.merged)
    ]
    if shown:
        print(table(shown))
        print()
        print(LEGEND)
    print(
        f"\n{len(found)} worktrees under {WORKTREE_DIR.as_posix()}, {len(shown)} shown; "
        f"{sum(1 for w in shown if w.verdict() == 'merged')} merged, "
        f"{sum(1 for w in shown if w.needs_typed_name)} dirty or unpushed"
    )
    if not args.execute:
        print("Nothing removed (dry run). Add --execute to be asked per worktree.")
        return 0
    if not shown:
        print("Nothing to ask about.")
        return 0
    if not sys.stdin.isatty():
        print("Refusing: no terminal to confirm on (removing is a human gate).", file=sys.stderr)
        return 2
    removed = sum(1 for wt in shown if confirm(wt, ask) and remove(wt))
    print(f"\n{removed} removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
