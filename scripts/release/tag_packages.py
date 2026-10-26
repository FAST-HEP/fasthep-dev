from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_data import PINNED_LAST, ReleasePlan, load_release_plan, run_git  # noqa: E402


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
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    plan = load_release_plan(args.release_file)
    if args.package is not None and args.package not in plan.packages:
        raise SystemExit(
            f"Unknown package {args.package!r}, expected one of {sorted(plan.packages)}"
        )
    tags = _selected_tags(root=root, plan=plan, package=args.package)

    if not tags:
        print("No packages selected.")
        return 0

    for item in tags:
        _create_or_report_tag(item, dry_run=args.dry_run, allow_existing=args.push)
        if args.push:
            _push_tag(item, dry_run=args.dry_run)

    if args.package is None:
        print()
        print(f"Stopped before tagging {' and '.join(PINNED_LAST)}.")
        print(
            "Their pins reference packages just tagged above, so update them now "
            "that those tags exist:"
        )
        print(
            f"  python scripts/release/update_versions.py releases.json --package {PINNED_LAST[0]}"
        )
        print("Then tag it:")
        print(
            f"  python scripts/release/tag_packages.py releases.json "
            f"--package {PINNED_LAST[0]} --push"
        )
    elif args.package == PINNED_LAST[0]:
        print()
        print(f"{PINNED_LAST[0]} tagged. Push it and wait for CI/docs to pass before continuing.")
        print(f"Once it's green, update {PINNED_LAST[-1]}'s pins the same way, then tag it last:")
        print(
            f"  python scripts/release/update_versions.py releases.json --package {PINNED_LAST[-1]}"
        )
        print(
            f"  python scripts/release/tag_packages.py releases.json "
            f"--package {PINNED_LAST[-1]} --push"
        )
    return 0


def _selected_tags(
    *,
    root: Path,
    plan: ReleasePlan,
    package: str | None,
) -> list[PackageTag]:
    if package is not None:
        keys = [package]
    else:
        keys = [key for key in plan.order if key not in PINNED_LAST]
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
    _bust_stale_editable_version_cache(item)


def _bust_stale_editable_version_cache(item: PackageTag) -> None:
    # pixi/uv treat an editable package's hatch-vcs version as valid until
    # pyproject.toml's mtime changes; a bare `git tag` doesn't touch it, so
    # without this, `pixi run` keeps resolving the pre-tag dev-snapshot
    # version indefinitely.
    pyproject = item.path / "pyproject.toml"
    if pyproject.exists():
        pyproject.touch()


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
