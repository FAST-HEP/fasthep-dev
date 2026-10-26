from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement

META_PACKAGE = "fasthep"

_FASTHEP_DIST_RE = re.compile(r"^fasthep(-.+)?$", re.IGNORECASE)
_CALENDAR_VERSION_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d+)$")


@dataclass(frozen=True, slots=True)
class PackageSpec:
    dist: str
    version: str


@dataclass(frozen=True, slots=True)
class ReleasePlan:
    packages: dict[str, PackageSpec]
    order: list[str]

    @property
    def release_version(self) -> str:
        return self.packages[META_PACKAGE].version


def load_release_plan(path: Path) -> ReleasePlan:
    with path.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)

    packages_raw = data.get("packages")
    if not isinstance(packages_raw, dict):
        raise SystemExit("releases.json must contain a packages object")

    packages: dict[str, PackageSpec] = {}
    for key, value in packages_raw.items():
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("dist"), str)
            or not isinstance(value.get("version"), str)
        ):
            raise SystemExit(f"packages.{key} must have string 'dist' and 'version'")
        packages[key] = PackageSpec(dist=value["dist"], version=value["version"])

    order = data.get("order")
    if not isinstance(order, list):
        raise SystemExit("releases.json must contain an order list")

    missing = set(order) - set(packages)
    if missing:
        raise SystemExit(f"Unknown package keys in release order: {sorted(missing)}")

    return ReleasePlan(packages=packages, order=order)


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _dependency_specs(pyproject_path: Path) -> list[str]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    specs: list[str] = list(project.get("dependencies") or [])
    for extra_deps in (project.get("optional-dependencies") or {}).values():
        specs.extend(extra_deps)
    return specs


def fasthep_dependency_keys(pyproject_path: Path, dist_to_key: dict[str, str]) -> set[str]:
    keys: set[str] = set()
    for spec in _dependency_specs(pyproject_path):
        try:
            requirement = Requirement(spec)
        except InvalidRequirement:
            continue
        key = dist_to_key.get(requirement.name.lower())
        if key is not None:
            keys.add(key)
    return keys


def validate_order(plan: ReleasePlan, root: Path) -> list[str]:
    dist_to_key = {spec.dist.lower(): key for key, spec in plan.packages.items()}
    errors: list[str] = []
    for index, key in enumerate(plan.order):
        pyproject = root / key / "pyproject.toml"
        if not pyproject.exists():
            continue
        for spec in _dependency_specs(pyproject):
            try:
                requirement = Requirement(spec)
            except InvalidRequirement:
                continue
            if not _FASTHEP_DIST_RE.match(requirement.name):
                continue
            dep_key = dist_to_key.get(requirement.name.lower())
            if dep_key is None:
                errors.append(
                    f"{key}: depends on '{requirement.name}', which is not in the release order"
                )
                continue
            if plan.order.index(dep_key) >= index:
                errors.append(
                    f"{key}: depends on '{dep_key}', which is not earlier in the release order"
                )
    return errors


def validate_calendar_version(key: str, latest_tag: str | None, candidate: str) -> list[str]:
    candidate_match = _CALENDAR_VERSION_RE.match(candidate)
    if candidate_match is None:
        return [f"{key}: version '{candidate}' is not in YYYY.MM.N calendar-version form"]
    year, month, patch = (int(candidate_match[1]), int(candidate_match[2]), int(candidate_match[3]))

    if latest_tag is None:
        if patch != 1:
            return [f"{key}: first release must start at patch 1, got '{candidate}'"]
        return []

    latest_match = _CALENDAR_VERSION_RE.match(latest_tag)
    if latest_match is None:
        return []

    latest_year, latest_month, latest_patch = (
        int(latest_match[1]),
        int(latest_match[2]),
        int(latest_match[3]),
    )

    if (year, month) < (latest_year, latest_month):
        return [f"{key}: version '{candidate}' goes backwards from latest tag '{latest_tag}'"]
    if (year, month) == (latest_year, latest_month):
        if patch != latest_patch + 1:
            return [
                f"{key}: same month as '{latest_tag}', expected patch {latest_patch + 1}, "
                f"got {patch}"
            ]
        return []
    if patch != 1:
        return [f"{key}: new month vs '{latest_tag}' must reset patch to 1, got {patch}"]
    return []


def latest_tag(path: Path) -> str | None:
    result = run_git(path, "tag", "--list", "20*.*.*", "--sort=-v:refname")
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines[0] if lines else None
