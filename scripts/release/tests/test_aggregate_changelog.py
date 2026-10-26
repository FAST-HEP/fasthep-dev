from __future__ import annotations

from pathlib import Path

from scripts.release.aggregate_changelog import build_aggregate, latest_changelog_section
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


def test_latest_changelog_section_extracts_first_block(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n\n## [2026.10.1] - 2026-10-26\n\n### Added\n- thing\n\n"
        "## [2026.08.2] - 2026-08-01\n\n### Fixed\n- old thing\n"
    )

    section = latest_changelog_section(path)

    assert section.startswith("## [2026.10.1] - 2026-10-26")
    assert "old thing" not in section


def test_latest_changelog_section_missing_file_returns_none(tmp_path):
    assert latest_changelog_section(tmp_path / "CHANGELOG.md") is None


def test_build_aggregate_skips_missing_changelogs_with_a_note(tmp_path, capsys):
    _write_pyproject(tmp_path / "toolbench", name="fasthep-toolbench", version="2026.10.1", deps=[])
    (tmp_path / "toolbench" / "CHANGELOG.md").write_text("## [2026.10.1] - 2026-10-26\n\n- a change\n")
    plan = _plan({"toolbench": "fasthep-toolbench", "fasthep": "fasthep"}, order=["toolbench", "fasthep"])

    aggregate = build_aggregate(plan, tmp_path)

    assert "toolbench" in aggregate.lower()
    assert "a change" in aggregate
    # "fasthep" itself has no CHANGELOG.md in this fixture and must be skipped, not crash
