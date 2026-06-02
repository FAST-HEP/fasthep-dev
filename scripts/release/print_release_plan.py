from __future__ import annotations

import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the FAST-HEP release plan.")
    parser.add_argument("release_file", type=Path)
    args = parser.parse_args()

    plan = _read_release(args.release_file)
    packages = dict(plan["packages"])
    order = list(plan["order"])

    print(f"Release: {plan['release']}")
    print()
    print("Package release order:")
    for index, key in enumerate(order, start=1):
        dist = PACKAGE_DISTS[key]
        version = packages[key]
        print(f"{index}. {key}")
        print(f"   path: {key}/")
        print(f"   distribution: {dist}")
        print(f"   version: {version}")
        print(f"   tag: {version}")

    print()
    print("Manual hard stops:")
    print("Push workshop first and wait for CI/docs to pass.")
    print("Only continue to fasthep once workshop is green.")
    print()
    print("All that remains after package tags is to tag fasthep.")
    return 0


def _read_release(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    _validate(data)
    return data


def _validate(data: dict[str, Any]) -> None:
    missing = set(data.get("order") or []) - set(PACKAGE_DISTS)
    if missing:
        raise SystemExit(f"Unknown package keys in release order: {sorted(missing)}")
    packages = data.get("packages")
    if not isinstance(packages, dict):
        raise SystemExit("releases.json must contain a packages object")
    for key in data.get("order") or []:
        if key not in packages:
            raise SystemExit(f"Missing version for package '{key}'")


if __name__ == "__main__":
    raise SystemExit(main())
