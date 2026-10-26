from __future__ import annotations

import argparse
from pathlib import Path

from release_data import load_release_plan, validate_order


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the FAST-HEP release plan.")
    parser.add_argument("release_file", type=Path)
    args = parser.parse_args()

    root = Path.cwd()
    plan = load_release_plan(args.release_file)

    errors = validate_order(plan, root)
    if errors:
        print("Release plan invalid:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"Release: {plan.release_version}")
    print()
    print("Package release order:")
    for index, key in enumerate(plan.order, start=1):
        spec = plan.packages[key]
        print(f"{index}. {key}")
        print(f"   path: {key}/")
        print(f"   distribution: {spec.dist}")
        print(f"   version: {spec.version}")
        print(f"   tag: {spec.version}")

    print()
    print("Manual hard stops:")
    print("Push workshop first and wait for CI/docs to pass.")
    print("Only continue to fasthep once workshop is green.")
    print()
    print("All that remains after package tags is to tag fasthep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
