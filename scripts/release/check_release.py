from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
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


@dataclass(frozen=True, slots=True)
class PackageCheck:
    key: str
    path: Path
    version: str

    @property
    def dist(self) -> str:
        return PACKAGE_DISTS[self.key]

    @property
    def tag(self) -> str:
        return self.version


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FAST-HEP release readiness.")
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--package", choices=sorted(PACKAGE_DISTS))
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()

    root = Path.cwd()
    plan = _read_release(args.release_file)
    selected = [args.package] if args.package else list(plan["order"])
    checks = [
        PackageCheck(key=key, path=root / key, version=plan["packages"][key])
        for key in selected
    ]

    errors: list[str] = []
    warnings: list[str] = []

    if not (root / "pixi.lock").exists():
        errors.append("workspace pixi.lock is missing")

    root_dirty = _git(root, "status", "--porcelain")
    if root_dirty.returncode == 0 and root_dirty.stdout.strip():
        warnings.append("workspace root has uncommitted changes")

    for check in checks:
        errors.extend(_check_package(check, expected_branch=args.branch))

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


def _read_release(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("packages"), dict):
        raise SystemExit("releases.json must contain a packages object")
    if not isinstance(data.get("order"), list):
        raise SystemExit("releases.json must contain an order list")
    return data


def _check_package(check: PackageCheck, *, expected_branch: str) -> list[str]:
    errors: list[str] = []
    if not check.path.exists():
        return [f"{check.key}: path does not exist: {check.path}"]
    inside = _git(check.path, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        errors.append(f"{check.key}: not a Git repository: {check.path}")
        return errors

    status = _git(check.path, "status", "--porcelain")
    if status.returncode != 0:
        errors.append(f"{check.key}: could not read Git status: {status.stderr.strip()}")
    elif status.stdout.strip():
        errors.append(f"{check.key}: working tree is not clean")

    branch = _git(check.path, "branch", "--show-current")
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
        package_errors = _check_pyproject(check, pyproject)
        errors.extend(package_errors)

    local_tag = _git(check.path, "tag", "--list", check.tag)
    if local_tag.returncode != 0:
        errors.append(f"{check.key}: could not list local tags: {local_tag.stderr.strip()}")
    elif local_tag.stdout.strip():
        errors.append(f"{check.key}: local tag already exists: {check.tag}")

    errors.extend(_check_remote_tag(check))
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


def _check_remote_tag(check: PackageCheck) -> list[str]:
    remote = _git(check.path, "remote", "get-url", "origin")
    if remote.returncode != 0 or not remote.stdout.strip():
        return []

    result = _git(
        check.path,
        "ls-remote",
        "--exit-code",
        "--tags",
        "origin",
        f"refs/tags/{check.tag}",
    )
    if result.returncode == 0:
        return [f"{check.key}: remote tag already exists: {check.tag}"]
    if result.returncode == 2:
        return []
    return [f"{check.key}: could not check remote tag {check.tag}: {result.stderr.strip()}"]


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
