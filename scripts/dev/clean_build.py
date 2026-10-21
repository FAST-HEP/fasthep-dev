#!/usr/bin/env python3
"""List and, on request, delete generated ``build/`` output below the workspace.

``build/`` directories are gitignored, so nothing in them is backed up and some of it
is validation material. This script therefore

* lists by default and deletes nothing (``--execute`` is needed);
* needs an explicit selection (``--older-than DAYS``, ``--all`` or ``--only GLOB``);
* works on the run directories inside each ``build/`` (use ``--whole`` for the folder);
* never deletes a directory that holds git-tracked files or that has a ``clean.keep`` file
  in it or in any folder above it (put an empty ``clean.keep`` into folders meant to stay);
* is a human gate: deleting asks for a typed confirmation on a terminal and refuses when there
  is none, and there is no option to skip it (an agent or a pipeline cannot confirm for you).

FAST-HEP only: ``hinv/`` (the CMS analysis integration) is not scanned; it has its own copy of
this tool inside ``hinv/chip``.
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", ".pixi", "node_modules", "__pycache__"}
EXCLUDED_TOP_LEVEL = {"hinv"}  # CMS analysis integration: not FAST-HEP, has its own tooling
KEEP_MARKER = "clean.keep"


@dataclass
class Entry:
    path: Path
    size: int
    age_days: float
    keep_reason: str | None = None
    selected: bool = False


def find_build_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            continue
        for child in children:
            if child.name in SKIP_DIRS or (current == root and child.name in EXCLUDED_TOP_LEVEL):
                continue
            if child.name == "build":
                found.append(child)
            else:
                stack.append(child)
    return sorted(found)


def dir_size(path: Path) -> tuple[int, float]:
    """Total bytes and newest modification time below ``path``."""
    total, newest = 0, path.stat().st_mtime
    for item in path.rglob("*"):
        try:
            stat = item.lstat()
        except OSError:
            continue
        newest = max(newest, stat.st_mtime)
        if item.is_file() and not item.is_symlink():
            total += stat.st_size
    return total, newest


def has_tracked_files(path: Path) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "ls-files", "--", "."],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(out.strip())


def keep_reason(path: Path, root: Path) -> str | None:
    """Why ``path`` must not be deleted, or None."""
    for folder in (path, *path.parents):
        if (folder / KEEP_MARKER).exists():
            return f"{KEEP_MARKER} in {folder.relative_to(root).as_posix() or '.'}"
        if folder == root:
            break
    if path.is_dir() and has_tracked_files(path):
        return "contains git-tracked files"
    return None


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "kB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{size} B"


def collect(root: Path, *, whole: bool) -> list[Entry]:
    now = time.time()
    targets: list[Path] = []
    for build in find_build_dirs(root):
        if whole:
            targets.append(build)
        else:
            targets.extend(sorted(p for p in build.iterdir() if p.is_dir() and not p.is_symlink()))
            targets.extend(sorted(p for p in build.iterdir() if p.is_file()))
    entries: list[Entry] = []
    for path in targets:
        if path.is_dir():
            size, newest = dir_size(path)
        else:
            stat = path.stat()
            size, newest = stat.st_size, stat.st_mtime
        entry = Entry(path, size, (now - newest) / 86400)
        entry.keep_reason = keep_reason(path, root)
        entries.append(entry)
    return entries


def select(entries: list[Entry], root: Path, args: argparse.Namespace) -> None:
    for entry in entries:
        rel = entry.path.relative_to(root).as_posix()
        chosen = args.all
        if args.older_than is not None and entry.age_days >= args.older_than:
            chosen = True
        if args.only and any(fnmatch.fnmatch(rel, pattern) for pattern in args.only):
            chosen = True
        entry.selected = chosen and entry.keep_reason is None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="workspace root (default: cwd)")
    parser.add_argument("--older-than", type=float, metavar="DAYS", help="select entries not modified for DAYS days")
    parser.add_argument("--all", action="store_true", help="select every unprotected entry")
    parser.add_argument("--only", action="append", metavar="GLOB", help="select entries matching GLOB (relative to root)")
    parser.add_argument("--whole", action="store_true", help="treat each build/ folder as one entry")
    parser.add_argument("--execute", action="store_true", help="delete the selected entries (default: list only)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    entries = collect(root, whole=args.whole)
    select(entries, root, args)

    print(f"{'entry':<64} {'size':>9} {'age(d)':>7}  status")
    for entry in entries:
        rel = entry.path.relative_to(root).as_posix()
        if entry.keep_reason:
            status = f"KEEP: {entry.keep_reason}"
        elif entry.selected:
            status = "selected" if args.execute else "would delete"
        else:
            status = "not selected"
        print(f"{rel:<64} {human(entry.size):>9} {entry.age_days:>7.1f}  {status}")
    chosen = [e for e in entries if e.selected]
    print(f"\n{len(entries)} entries, {sum(e.size for e in entries) and human(sum(e.size for e in entries))} in total; "
          f"{len(chosen)} selected ({human(sum(e.size for e in chosen))}); "
          f"{sum(1 for e in entries if e.keep_reason)} protected")

    if not args.execute:
        print("Nothing deleted (dry run). Select with --older-than/--all/--only and add --execute.")
        return 0
    if not (args.older_than is not None or args.all or args.only):
        print("Refusing: --execute needs --older-than, --all or --only.", file=sys.stderr)
        return 2
    if not chosen:
        print("Nothing selected.")
        return 0
    if not sys.stdin.isatty():
        print("Refusing: no terminal to confirm on (deleting is a human gate).", file=sys.stderr)
        return 2
    if input(f"Type 'delete' to remove {len(chosen)} entries: ").strip() != "delete":
        print("Aborted.")
        return 1
    for entry in chosen:
        if entry.path.is_dir():
            shutil.rmtree(entry.path)
        else:
            entry.path.unlink()
        print("deleted", entry.path.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
