"""Keep every package's ``.github/dependabot.yml`` equal to the shared template.

Dependabot has no inheritance, so the config is a copy in each repository. The template is
``templates/dependabot.yml`` of the ``dot-github`` submodule (FAST-HEP/.github); the packages are
those in ``releases.json``. Default is a dry run: it shows each file as same, different (with the
diff) or missing. ``--write`` writes the template into the working trees only: it does not commit
or push, and it refuses a package whose ``dependabot.yml`` already has uncommitted changes.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path("dot-github") / "templates" / "dependabot.yml"
TARGET = Path(".github") / "dependabot.yml"


def packages(release_file: Path) -> list[str]:
    plan = json.loads(release_file.read_text(encoding="utf-8"))
    return list(plan["order"])


def is_modified(repo: Path, relative: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--", str(relative)],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--release-file", type=Path, default=Path("releases.json"))
    parser.add_argument("--write", action="store_true", help="write the template (default: dry run)")
    args = parser.parse_args(argv)

    template_path = args.root / TEMPLATE
    if not template_path.exists():
        print(f"template missing: {template_path} (git submodule update --init dot-github)", file=sys.stderr)
        return 2
    template = template_path.read_text(encoding="utf-8")
    release_file = args.release_file if args.release_file.is_absolute() else args.root / args.release_file

    refused = 0
    changed = 0
    for key in packages(release_file):
        repo = args.root / key
        target = repo / TARGET
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == template:
            print(f"same      {key}")
            continue
        status = "missing" if current is None else "different"
        print(f"{status:9} {key}")
        if current is not None:
            diff = difflib.unified_diff(
                current.splitlines(), template.splitlines(), f"{key} (now)", "template", lineterm=""
            )
            lines = [f"    {line}" for line in diff]
            print("\n".join(lines) if lines else "    (differs only in the final newline)")
        if not args.write:
            continue
        if current is not None and is_modified(repo, TARGET):
            print(f"  refused: {target} has uncommitted changes", file=sys.stderr)
            refused += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template, encoding="utf-8")
        changed += 1
        print("  written")

    if not args.write:
        print("dry run: nothing written; re-run with --write")
    else:
        print(f"{changed} file(s) written (not committed), {refused} refused")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
