"""Create the GitHub Releases that tags made before the release job existed never got.

For every package, every calendar-version tag from ``--since`` on that has no release yet gets one
whose notes are the package's own ``## [X]`` changelog section (read from the working tree) plus the
PyPI link. A tag without a changelog section is listed and skipped, never invented.

Default is a dry run (it only reads: ``gh release list``). ``--execute`` creates the releases after
a typed confirmation on a terminal; without a terminal it refuses, so an agent or a pipeline cannot
publish for you (human gate: releases are public and appear in watchers' feeds). The newest tag of
a repository is marked latest, older ones are not. ``gh`` authenticates itself (``gh auth login``
or the token file you name for the session in ``GH_TOKEN``); this script never reads a token.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from changelog_tools import ToolFailure, release_notes  # noqa: E402
from release_data import load_release_plan, run_git  # noqa: E402

_VERSION_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d+)$")
DEFAULT_SINCE = "2026.10.0"


@dataclass(slots=True)
class Item:
    key: str
    slug: str
    tag: str
    action: str  # create | exists | no-section
    notes: str = ""
    latest: bool = False
    detail: str = ""


def _vkey(tag: str) -> tuple[int, int, int]:
    match = _VERSION_RE.match(tag)
    assert match is not None
    return int(match[1]), int(match[2]), int(match[3])


def repo_slug(repo: Path) -> str | None:
    url = run_git(repo, "remote", "get-url", "origin").stdout.strip()
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match[1] if match else None


def calendar_tags(repo: Path, since: str) -> list[str]:
    tags = [
        line.strip()
        for line in run_git(repo, "tag", "--list").stdout.splitlines()
        if _VERSION_RE.match(line.strip())
    ]
    return sorted((t for t in tags if _vkey(t) >= _vkey(since)), key=_vkey)


def existing_releases(slug: str) -> set[str]:
    result = subprocess.run(
        ["gh", "release", "list", "--repo", slug, "--limit", "200", "--json", "tagName"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"{slug}: gh release list failed: {result.stderr.strip()}")
    return {entry["tagName"] for entry in json.loads(result.stdout)}


def plan_items(root: Path, release_file: Path, since: str, only: str | None) -> list[Item]:
    plan = load_release_plan(release_file)
    items: list[Item] = []
    for key in plan.order:
        if only and key != only:
            continue
        repo = root / key
        slug = repo_slug(repo)
        if slug is None:
            raise SystemExit(f"{key}: cannot read the origin remote of {repo}")
        tags = calendar_tags(repo, since)
        have = existing_releases(slug)
        for tag in tags:
            if tag in have:
                items.append(Item(key, slug, tag, "exists"))
                continue
            try:
                notes = release_notes(root, repo / "CHANGELOG.md", tag, plan.packages[key].dist)
            except ToolFailure as exc:
                items.append(Item(key, slug, tag, "no-section", detail=str(exc).splitlines()[0]))
                continue
            items.append(Item(key, slug, tag, "create", notes=notes, latest=tag == tags[-1]))
    return items


def print_plan(items: list[Item]) -> None:
    for item in items:
        extra = f"  ({item.detail})" if item.detail else ""
        print(f"{item.action:10} {item.slug} {item.tag}{extra}")
    todo = sum(i.action == "create" for i in items)
    skipped = [i for i in items if i.action == "no-section"]
    print(f"\n{todo} release(s) to create, {len(skipped)} tag(s) without a changelog section")


def create(item: Item) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(item.notes)
    cmd = [
        "gh", "release", "create", item.tag, "--repo", item.slug, "--verify-tag",
        "--title", item.tag, "--notes-file", handle.name,
        "--latest=true" if item.latest else "--latest=false",
    ]  # fmt: skip
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    Path(handle.name).unlink(missing_ok=True)
    print(f"{'created' if result.returncode == 0 else 'FAILED '} {item.slug} {item.tag}")
    if result.returncode != 0:
        print(f"  {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--since", default=DEFAULT_SINCE, help="oldest tag version (default: %(default)s)")
    parser.add_argument("--package", help="only this package key")
    parser.add_argument("--execute", action="store_true", help="create the releases (human gate)")
    args = parser.parse_args()

    if _VERSION_RE.match(args.since) is None:
        raise SystemExit(f"--since must look like YYYY.MM.N, got {args.since!r}")
    items = plan_items(Path.cwd(), args.release_file, args.since, args.package)
    print_plan(items)
    todo = [i for i in items if i.action == "create"]
    if not args.execute or not todo:
        return 0
    if not sys.stdin.isatty():
        print("Refusing: no terminal to confirm on (publishing releases is a human gate).", file=sys.stderr)
        return 2
    if input(f"Type 'release' to publish {len(todo)} public release(s): ").strip() != "release":
        print("Aborted.")
        return 1
    failed = sum(not create(item) for item in todo)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
