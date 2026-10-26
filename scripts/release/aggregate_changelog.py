from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_data import META_PACKAGE, ReleasePlan, load_release_plan  # noqa: E402

_HEADING_RE = re.compile(r"(?m)^## \[.*$")


def latest_changelog_section(changelog_path: Path) -> str | None:
    if not changelog_path.exists():
        return None
    text = changelog_path.read_text(encoding="utf-8")
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return None
    start = headings[0].start()
    end = headings[1].start() if len(headings) > 1 else len(text)
    return text[start:end].rstrip() + "\n"


def build_aggregate(plan: ReleasePlan, root: Path) -> str:
    blocks: list[str] = []
    for key in plan.order:
        if key == META_PACKAGE:
            continue
        section = latest_changelog_section(root / key / "CHANGELOG.md")
        if section is None:
            print(f"note: no CHANGELOG.md yet for {key}, skipping", file=sys.stderr)
            continue
        body = "\n".join(section.splitlines()[1:]).strip()
        blocks.append(f"### {plan.packages[key].dist}\n\n{body}\n")

    heading = f"## [{plan.release_version}] - {date.today().isoformat()}\n\n"
    return heading + "\n".join(blocks) + ("\n" if blocks else "")


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
    title_line = "# Changelog\n"
    if fasthep_changelog.exists():
        existing = fasthep_changelog.read_text(encoding="utf-8")
        rest = existing[len(title_line):] if existing.startswith(title_line) else existing
    else:
        rest = ""

    updated = title_line + "\n" + aggregate + "\n" + rest.lstrip("\n")
    fasthep_changelog.parent.mkdir(parents=True, exist_ok=True)
    fasthep_changelog.write_text(updated, encoding="utf-8")
    print(f"Updated {fasthep_changelog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
