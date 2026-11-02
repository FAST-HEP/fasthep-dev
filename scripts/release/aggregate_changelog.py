from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_data import META_PACKAGE, ReleasePlan, load_release_plan  # noqa: E402

_HEADING_RE = re.compile(r"(?m)^## \[.*$")


def changelog_section(changelog_path: Path, version: str) -> str | None:
    """The `## [<version>]` block of a changelog, or None if the file or the section is missing.

    Selected by version, not by position: `## [Unreleased]` comes first and is empty (or, if it
    was never split at release time, holds entries that belong to an older version).
    """
    if not changelog_path.exists():
        return None
    text = changelog_path.read_text(encoding="utf-8")
    headings = list(_HEADING_RE.finditer(text))
    for index, heading in enumerate(headings):
        if heading.group(0).startswith(f"## [{version}]"):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            return text[heading.start() : end].rstrip() + "\n"
    return None


def build_aggregate(plan: ReleasePlan, root: Path) -> str:
    blocks: list[str] = []
    for key in plan.order:
        if key == META_PACKAGE:
            continue
        spec = plan.packages[key]
        if spec.version != plan.release_version:
            # New version == changes: a package left at an older version has none in this release.
            blocks.append(f"### {spec.dist}\n\nUnchanged: stays at {spec.version}.\n")
            continue
        changelog_path = root / key / "CHANGELOG.md"
        if not changelog_path.exists():
            print(f"note: no CHANGELOG.md yet for {key}, skipping", file=sys.stderr)
            continue
        section = changelog_section(changelog_path, spec.version)
        if section is None:
            raise SystemExit(
                f"{spec.dist}: {changelog_path} has no '## [{spec.version}]' section; "
                "split [Unreleased] before aggregating"
            )
        # Categories (### Added ...) nest one level below the package heading.
        body = "\n".join(
            f"#{line}" if line.startswith("### ") else line for line in section.splitlines()[1:]
        ).strip()
        blocks.append(f"### {spec.dist}\n\n{body}\n")

    heading = f"## [{plan.release_version}] - {date.today().isoformat()}\n\n"
    return heading + "\n".join(blocks) + ("\n" if blocks else "")


def insert_release(existing: str, aggregate: str) -> str:
    """Put the aggregated release under `## [Unreleased]`, above the older releases."""
    headings = list(_HEADING_RE.finditer(existing))
    if headings and headings[0].group(0).startswith("## [Unreleased]"):
        position = headings[1].start() if len(headings) > 1 else len(existing)
    elif headings:
        position = headings[0].start()
    else:
        position = len(existing)
    head = existing[:position].rstrip("\n")
    tail = existing[position:].lstrip("\n")
    return head + "\n\n" + aggregate.rstrip("\n") + "\n" + ("\n" + tail if tail else "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate FAST-HEP package changelogs into fasthep/CHANGELOG.md."
    )
    parser.add_argument("release_file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    plan = load_release_plan(args.release_file)
    aggregate = build_aggregate(plan, root)

    if args.dry_run:
        print(aggregate)
        return 0

    fasthep_changelog = root / "fasthep" / "CHANGELOG.md"
    existing = (
        fasthep_changelog.read_text(encoding="utf-8")
        if fasthep_changelog.exists()
        else "# Changelog\n\n## [Unreleased]\n"
    )
    updated = insert_release(existing, aggregate)
    fasthep_changelog.parent.mkdir(parents=True, exist_ok=True)
    fasthep_changelog.write_text(updated, encoding="utf-8")
    print(f"Updated {fasthep_changelog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
