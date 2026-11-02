from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release.aggregate_changelog import (
    build_aggregate,
    changelog_section,
    insert_release,
)
from scripts.release.release_data import PackageSpec, ReleasePlan


def _write_pyproject(path: Path, *, name: str, version: str, deps: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    deps_text = ",\n".join(f'    "{dep}"' for dep in deps)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\ndependencies = [\n{deps_text}\n]\n',
        encoding="utf-8",
    )


def _plan(dists: dict[str, str], order: list[str]) -> ReleasePlan:
    packages = {key: PackageSpec(dist=dist, version="2026.10.1") for key, dist in dists.items()}
    return ReleasePlan(packages=packages, order=order)


def test_changelog_section_selects_the_requested_version_not_the_first_heading(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [2026.11.1] - 2026-11-02\n\n### Added\n- new thing\n\n"
        "## [2026.10.1] - 2026-10-26\n\n### Fixed\n- old thing\n"
    )

    section = changelog_section(path, "2026.11.1")

    assert section.startswith("## [2026.11.1] - 2026-11-02")
    assert "new thing" in section
    assert "old thing" not in section


def test_changelog_section_returns_none_when_the_version_has_no_section(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text("## [Unreleased]\n\n- an unsplit entry\n\n## [2026.08.2] - 2026-08-01\n\n- x\n")

    assert changelog_section(path, "2026.11.1") is None


def test_changelog_section_missing_file_returns_none(tmp_path):
    assert changelog_section(tmp_path / "CHANGELOG.md", "2026.10.1") is None


def test_build_aggregate_skips_missing_changelogs_with_a_note(tmp_path, capsys):
    _write_pyproject(tmp_path / "toolbench", name="fasthep-toolbench", version="2026.10.1", deps=[])
    (tmp_path / "toolbench" / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [2026.10.1] - 2026-10-26\n\n- a change\n"
    )
    plan = _plan({"toolbench": "fasthep-toolbench", "fasthep": "fasthep"}, order=["toolbench", "fasthep"])

    aggregate = build_aggregate(plan, tmp_path)

    assert "toolbench" in aggregate.lower()
    assert "a change" in aggregate
    # "fasthep" itself has no CHANGELOG.md in this fixture and must be skipped, not crash


def test_build_aggregate_lists_a_package_left_at_an_older_version_as_unchanged(tmp_path):
    for key, dist in (("toolbench", "fasthep-toolbench"), ("curator", "fasthep-curator")):
        _write_pyproject(tmp_path / key, name=dist, version="x", deps=[])
    (tmp_path / "toolbench" / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [2026.11.1] - 2026-11-02\n\n### Added\n\n- a toolbench change\n\n"
        "## [2026.10.1] - 2026-10-26\n\n- an old change\n"
    )
    (tmp_path / "curator" / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n## [2026.10.1] - 2026-10-26\n\n- an old curator change\n"
    )
    plan = ReleasePlan(
        packages={
            "toolbench": PackageSpec(dist="fasthep-toolbench", version="2026.11.1"),
            "curator": PackageSpec(dist="fasthep-curator", version="2026.10.1"),
            "fasthep": PackageSpec(dist="fasthep", version="2026.11.1"),
        },
        order=["toolbench", "curator", "fasthep"],
    )

    aggregate = build_aggregate(plan, tmp_path)

    assert "a toolbench change" in aggregate
    assert "### fasthep-toolbench\n\n#### Added\n" in aggregate
    assert "an old change" not in aggregate
    assert "an old curator change" not in aggregate
    assert "### fasthep-curator\n\nUnchanged: stays at 2026.10.1." in aggregate


def test_build_aggregate_refuses_a_package_whose_changelog_has_no_section_for_the_release(tmp_path):
    _write_pyproject(tmp_path / "flow", name="fasthep-flow", version="x", deps=[])
    (tmp_path / "flow" / "CHANGELOG.md").write_text("## [Unreleased]\n\n- an unsplit entry\n")
    plan = ReleasePlan(
        packages={
            "flow": PackageSpec(dist="fasthep-flow", version="2026.11.1"),
            "fasthep": PackageSpec(dist="fasthep", version="2026.11.1"),
        },
        order=["flow", "fasthep"],
    )

    with pytest.raises(SystemExit, match="fasthep-flow.*2026.11.1"):
        build_aggregate(plan, tmp_path)


def test_insert_release_goes_under_unreleased_and_above_older_releases():
    existing = (
        "# Changelog\n\nIntro text.\n\n## [Unreleased]\n\n## [2026.08.2] - 2026-08-25\n\n- old\n"
    )

    updated = insert_release(existing, "## [2026.11.1] - 2026-11-02\n\n### fasthep-flow\n\n- new\n")

    assert updated.index("Intro text.") < updated.index("## [Unreleased]")
    assert updated.index("## [Unreleased]") < updated.index("## [2026.11.1]")
    assert updated.index("## [2026.11.1]") < updated.index("## [2026.08.2]")
