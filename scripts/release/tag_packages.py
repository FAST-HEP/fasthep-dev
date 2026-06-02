from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_DISTS = {
    "flow": "fasthep-flow",
    "carpenter": "fasthep-carpenter",
    "curator": "fasthep-curator",
    "render": "fasthep-render",
    "cli": "fasthep-cli",
    "toolbench": "fasthep-toolbench",
    "workshop": "fasthep-workshop",
    "fasthep": "fasthep",
}

META_PACKAGE = "fasthep"


@dataclass(frozen=True, slots=True)
class PackageTag:
    key: str
    path: Path
    version: str

    @property
    def dist(self) -> str:
        return PACKAGE_DISTS[self.key]

    @property
    def tag(self) -> str:
        return self.version

    @property
    def message(self) -> str:
        return f"Release {self.dist} {self.version}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create FAST-HEP release tags.")
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--package", choices=sorted(PACKAGE_DISTS))
    parser.add_argument("--include-meta", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    plan = _read_release(args.release_file)
    tags = _selected_tags(
        root=root,
        plan=plan,
        package=args.package,
        include_meta=args.include_meta,
    )

    if not tags:
        print("No packages selected.")
        return 0

    for item in tags:
        _create_or_report_tag(item, dry_run=args.dry_run, allow_existing=args.push)
        if args.push:
            _push_tag(item, dry_run=args.dry_run)

    if args.package != META_PACKAGE and not args.include_meta:
        print()
        print("Stopped before tagging fasthep meta package.")
        print("Push workshop first and wait for CI/docs to pass.")
        print("Only continue to fasthep once workshop is green.")
        print(
            "Final step: python scripts/release/tag_packages.py "
            "releases.json --package fasthep --push"
        )
    return 0


def _read_release(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("packages"), dict):
        raise SystemExit("releases.json must contain a packages object")
    if not isinstance(data.get("order"), list):
        raise SystemExit("releases.json must contain an order list")
    return data


def _selected_tags(
    *,
    root: Path,
    plan: dict[str, Any],
    package: str | None,
    include_meta: bool,
) -> list[PackageTag]:
    if package is not None:
        keys = [package]
    else:
        keys = [
            key
            for key in plan["order"]
            if include_meta or key != META_PACKAGE
        ]
    return [
        PackageTag(key=key, path=root / key, version=plan["packages"][key])
        for key in keys
    ]


def _create_or_report_tag(
    item: PackageTag,
    *,
    dry_run: bool,
    allow_existing: bool,
) -> None:
    if not item.path.exists():
        raise SystemExit(f"{item.key}: path does not exist: {item.path}")

    exists = _git(item.path, "tag", "--list", item.tag)
    if exists.returncode != 0:
        raise SystemExit(f"{item.key}: could not list tags: {exists.stderr.strip()}")
    if exists.stdout.strip():
        if allow_existing:
            print(f"Using existing local tag {item.tag} in {item.key}/")
            return
        raise SystemExit(f"{item.key}: local tag already exists: {item.tag}")

    cmd = ["git", "tag", "-a", item.tag, "-m", item.message]
    if dry_run:
        print(f"[dry-run] ({item.key}) {' '.join(cmd)}")
        return

    result = subprocess.run(cmd, cwd=item.path, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{item.key}: failed to create tag: {result.stderr.strip()}")
    print(f"Created {item.tag} in {item.key}/")


def _push_tag(item: PackageTag, *, dry_run: bool) -> None:
    cmd = ["git", "push", "origin", item.tag]
    if dry_run:
        print(f"[dry-run] ({item.key}) {' '.join(cmd)}")
        return

    result = subprocess.run(cmd, cwd=item.path, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{item.key}: failed to push tag: {result.stderr.strip()}")
    print(f"Pushed {item.tag} from {item.key}/")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
