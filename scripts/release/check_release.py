from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass
from pathlib import Path

from release_data import (
    ReleasePlan,
    latest_tag,
    load_release_plan,
    run_git,
    validate_calendar_version,
    validate_order,
    validate_workshop_pins,
)


@dataclass(frozen=True, slots=True)
class PackageCheck:
    key: str
    path: Path
    dist: str
    version: str

    @property
    def tag(self) -> str:
        return self.version


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FAST-HEP release readiness.")
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--package")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()

    root = Path.cwd()
    plan = load_release_plan(args.release_file)
    if args.package is not None and args.package not in plan.packages:
        raise SystemExit(
            f"Unknown package {args.package!r}, expected one of {sorted(plan.packages)}"
        )
    selected = [args.package] if args.package else list(plan.order)
    checks = [
        PackageCheck(
            key=key,
            path=root / key,
            dist=plan.packages[key].dist,
            version=plan.packages[key].version,
        )
        for key in selected
    ]

    errors: list[str] = []
    warnings: list[str] = []

    if not (root / "pixi.lock").exists():
        errors.append("workspace pixi.lock is missing")

    root_dirty = run_git(root, "status", "--porcelain")
    if root_dirty.returncode == 0 and root_dirty.stdout.strip():
        warnings.append("workspace root has uncommitted changes")

    errors.extend(validate_order(plan, root))
    errors.extend(validate_workshop_pins(plan, root))

    for check in checks:
        errors.extend(_check_package(check, plan, expected_branch=args.branch))

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    if errors:
        print("Release check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Release check passed.")
    return 0


def _check_package(check: PackageCheck, plan: ReleasePlan, *, expected_branch: str) -> list[str]:
    if not check.path.exists():
        return [f"{check.key}: path does not exist: {check.path}"]
    inside = run_git(check.path, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return [f"{check.key}: not a Git repository: {check.path}"]

    local_tag = run_git(check.path, "tag", "--list", check.tag)
    if local_tag.returncode != 0:
        return [f"{check.key}: could not list local tags: {local_tag.stderr.strip()}"]

    remote_tag_exists, remote_errors = _remote_tag_exists(check)
    if remote_errors:
        return remote_errors

    if local_tag.stdout.strip() or remote_tag_exists:
        # Already tagged for this release cycle: nothing further to verify.
        return []

    errors: list[str] = []

    status = run_git(check.path, "status", "--porcelain")
    if status.returncode != 0:
        errors.append(f"{check.key}: could not read Git status: {status.stderr.strip()}")
    elif status.stdout.strip():
        errors.append(f"{check.key}: working tree is not clean")

    branch = run_git(check.path, "branch", "--show-current")
    if branch.returncode != 0:
        errors.append(f"{check.key}: could not read Git branch: {branch.stderr.strip()}")
    else:
        current = branch.stdout.strip()
        if current != expected_branch:
            errors.append(
                f"{check.key}: branch is '{current or 'detached'}', expected '{expected_branch}'"
            )

    pyproject = check.path / "pyproject.toml"
    if not pyproject.exists():
        errors.append(f"{check.key}: pyproject.toml is missing")
    else:
        errors.extend(_check_pyproject(check, pyproject))

    errors.extend(validate_calendar_version(check.key, latest_tag(check.path), check.version))
    return errors


def _check_pyproject(check: PackageCheck, pyproject: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"{check.key}: could not parse pyproject.toml: {exc}"]

    project = data.get("project") or {}
    name = project.get("name")
    if name != check.dist:
        errors.append(f"{check.key}: project.name is {name!r}, expected {check.dist!r}")

    version = project.get("version")
    if version is None:
        if "version" in set(project.get("dynamic") or []):
            # hatch-vcs resolves the real version from the git tag, not from
            # fallback_version; update_versions.py never rewrites it (see
            # release_data.PINNED_LAST / update_versions.py), so comparing it
            # here would always flag it as stale.
            return errors
        version = (
            data.get("tool", {})
            .get("hatch", {})
            .get("version", {})
            .get("raw-options", {})
            .get("fallback_version")
        )
    if version != check.version:
        errors.append(
            f"{check.key}: version is {version!r}, expected {check.version!r}"
        )
    return errors


def _remote_tag_exists(check: PackageCheck) -> tuple[bool, list[str]]:
    remote = run_git(check.path, "remote", "get-url", "origin")
    if remote.returncode != 0 or not remote.stdout.strip():
        return False, []

    result = run_git(
        check.path,
        "ls-remote",
        "--exit-code",
        "--tags",
        "origin",
        f"refs/tags/{check.tag}",
    )
    if result.returncode == 0:
        return True, []
    if result.returncode == 2:
        return False, []
    return False, [f"{check.key}: could not check remote tag {check.tag}: {result.stderr.strip()}"]


if __name__ == "__main__":
    raise SystemExit(main())
