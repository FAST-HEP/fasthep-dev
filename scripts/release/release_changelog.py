"""Changelog step of the release procedure: draft with git-cliff, insert, check the contract.

Subcommands (all take ``releases.json``):

``write``  Draft the ``## [X]`` section of every package that is about to be released (its version
           in ``releases.json`` is not tagged yet) and insert it under ``## [Unreleased]``. Dry run
           unless ``--write``; ``--write`` changes the files and commits each one locally
           (``docs(changelog): add X release``). Nothing is written unless every package drafts.
``check``  The changelog contract for every package: a dated, non-empty ``## [X]`` section, an empty
           ``## [Unreleased]``, and for ``fasthep`` an aggregated block that matches the packages.

``fasthep`` is not drafted: its changelog is aggregated (``aggregate_changelog.py``).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate_changelog import build_aggregate, changelog_section  # noqa: E402
from changelog_tools import (  # noqa: E402
    ToolFailure,
    check_contract,
    draft_section,
    insert_section,
)
from release_data import META_PACKAGE, ReleasePlan, load_release_plan, run_git  # noqa: E402

_BULLET_RE = re.compile(r"(?m)^- ")


def is_tagged(root: Path, key: str, version: str) -> bool:
    return bool(run_git(root / key, "tag", "--list", version).stdout.strip())


def cmd_write(root: Path, plan: ReleasePlan, *, write: bool) -> int:
    drafts: dict[str, tuple[str, str]] = {}
    errors: list[str] = []
    for key in plan.order:
        if key == META_PACKAGE:
            continue
        version = plan.packages[key].version
        repo = root / key
        if is_tagged(root, key, version):
            warning = _unreleased_changes(root, repo, key, version)
            print(f"{key}: stays at {version} (already tagged){warning}")
            continue
        changelog = repo / "CHANGELOG.md"
        if not changelog.exists():
            errors.append(f"{key}: {changelog} does not exist")
            continue
        try:
            section = draft_section(root, repo, version)
            updated = insert_section(root, changelog, version, section)
        except ToolFailure as exc:
            errors.append(f"{key}: {exc}")
            continue
        drafts[key] = (section, updated)

    for key, (section, _) in drafts.items():
        print(f"\n=== {key} {plan.packages[key].version}")
        print(section)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print("Nothing written: fix the packages above first.", file=sys.stderr)
        return 1
    if not drafts:
        print("\nNo package to release.")
        return 0
    if not write:
        print(f"\ndry run: {len(drafts)} changelog(s) would change; re-run with --write")
        return 0

    for key, (_, updated) in drafts.items():
        version = plan.packages[key].version
        (root / key / "CHANGELOG.md").write_text(updated, encoding="utf-8")
        _commit(root / key, key, version)
    print(f"\nWrote and committed {len(drafts)} changelog(s) locally. Review, push, merge.")
    return 0


def _unreleased_changes(root: Path, repo: Path, key: str, version: str) -> str:
    """A hint when a package kept its version although it has visible commits since the tag."""
    try:
        section = draft_section(root, repo, "next")
    except ToolFailure:
        return ""
    count = len(_BULLET_RE.findall(section))
    return f"\n  warning: {count} visible commit(s) since {version}; bump {key} in releases.json?"


def _commit(repo: Path, key: str, version: str) -> None:
    message = f"docs(changelog): add {version} release"
    run_git(repo, "add", "CHANGELOG.md")
    result = run_git(repo, "commit", "-m", message, "--", "CHANGELOG.md")
    if result.returncode != 0:
        raise SystemExit(f"{key}: commit failed: {(result.stderr or result.stdout).strip()}")
    print(f"{key}: committed {message!r}")


def cmd_check(root: Path, plan: ReleasePlan) -> int:
    failed = 0
    for key in plan.order:
        spec = plan.packages[key]
        problems = check_contract(root, root / key / "CHANGELOG.md", spec.version)
        if key == META_PACKAGE and not problems:
            problems = _aggregate_problems(root, plan)
        status = "ok" if not problems else "FAIL"
        print(f"{status:4} {key} {spec.version}")
        for problem in problems:
            print(f"       {problem}")
        failed += bool(problems)
    return 1 if failed else 0


def _aggregate_problems(root: Path, plan: ReleasePlan) -> list[str]:
    version = plan.release_version
    existing = changelog_section(root / META_PACKAGE / "CHANGELOG.md", version)
    try:
        expected = build_aggregate(plan, root)
    except SystemExit as exc:
        return [f"cannot rebuild the aggregate: {exc}"]
    # The heading carries a date; compare the bodies.
    def body(text: str) -> str:
        return "\n".join(text.splitlines()[1:]).strip()

    if body(existing or "") != body(expected):
        message = (
            f"the `## [{version}]` block differs from the packages' sections: "
            "re-run release-aggregate-changelog"
        )
        return [message]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("release_file", type=Path)
    parser.add_argument("command", choices=("write", "check"))
    parser.add_argument("--write", action="store_true", help="write and commit (write only)")
    args = parser.parse_args()
    root = Path.cwd()
    plan = load_release_plan(args.release_file)
    if args.command == "check":
        return cmd_check(root, plan)
    return cmd_write(root, plan, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
