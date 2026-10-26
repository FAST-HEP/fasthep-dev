from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

META_PACKAGE = "fasthep"


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
