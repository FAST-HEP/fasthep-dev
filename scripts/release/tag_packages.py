from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_data import META_PACKAGE, ReleasePlan, load_release_plan, run_git  # noqa: E402


@dataclass(frozen=True, slots=True)
class PackageTag:
    key: str
    path: Path
    dist: str
    version: str

    @property
    def tag(self) -> str:
        return self.version

    @property
    def message(self) -> str:
        return f"Release {self.dist} {self.version}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create FAST-HEP release tags.")
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--package")
    parser.add_argument("--include-meta", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    plan = load_release_plan(args.release_file)
    if args.package is not None and args.package not in plan.packages:
        raise SystemExit(
            f"Unknown package {args.package!r}, expected one of {sorted(plan.packages)}"
        )
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


def _selected_tags(
    *,
    root: Path,
    plan: ReleasePlan,
    package: str | None,
    include_meta: bool,
) -> list[PackageTag]:
    if package is not None:
        keys = [package]
    else:
        keys = [key for key in plan.order if include_meta or key != META_PACKAGE]
    return [
        PackageTag(
            key=key,
            path=root / key,
            dist=plan.packages[key].dist,
            version=plan.packages[key].version,
        )
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

    exists = run_git(item.path, "tag", "--list", item.tag)
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


if __name__ == "__main__":
    raise SystemExit(main())
