from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts.release.update_versions import _update_dependency_pins_text, _update_pixi_pins_text


DIST_VERSIONS = {
    "fasthep-flow": "2026.06.1",
    "fasthep-render": "2026.06.1",
    "fasthep-workshop": "2026.06.1",
}


def test_project_name_is_not_rewritten() -> None:
    text = """
[project]
name = "fasthep-workshop"
dependencies = [
    "fasthep-flow",
]
"""

    updated = _update_dependency_pins_text(text, DIST_VERSIONS)
    parsed = tomllib.loads(updated)

    assert parsed["project"]["name"] == "fasthep-workshop"


def test_project_dependencies_are_pinned() -> None:
    text = """
[project]
name = "example"
dependencies = [
    "fasthep-flow",
]
"""

    updated = _update_dependency_pins_text(text, DIST_VERSIONS)
    parsed = tomllib.loads(updated)

    assert parsed["project"]["dependencies"] == ["fasthep-flow == 2026.06.1"]


def test_optional_dependencies_are_pinned() -> None:
    text = """
[project]
name = "example"

[project.optional-dependencies]
docs = [
    "fasthep-render",
]
"""

    updated = _update_dependency_pins_text(text, DIST_VERSIONS)
    parsed = tomllib.loads(updated)

    assert parsed["project"]["optional-dependencies"]["docs"] == [
        "fasthep-render == 2026.06.1"
    ]


def test_unrelated_dependencies_are_unchanged() -> None:
    text = """
[project]
name = "example"
dependencies = [
    "numpy",
    "awkward >= 2",
]
"""

    updated = _update_dependency_pins_text(text, DIST_VERSIONS)
    parsed = tomllib.loads(updated)

    assert parsed["project"]["dependencies"] == ["numpy", "awkward >= 2"]


def test_extras_and_markers_are_preserved() -> None:
    text = """
[project]
name = "example"
dependencies = [
    "fasthep-flow[docs]; python_version >= '3.12'",
]
"""

    updated = _update_dependency_pins_text(text, DIST_VERSIONS)
    parsed = tomllib.loads(updated)

    assert parsed["project"]["dependencies"] == [
        "fasthep-flow[docs] == 2026.06.1; python_version >= \"3.12\""
    ]


def test_pixi_pins_rewritten_table_form() -> None:
    text = '[feature.released.pypi-dependencies]\nfasthep-flow = {version = ">=2026.08.3"}\n'

    updated = _update_pixi_pins_text(text, {"fasthep-flow": "2026.10.1"})

    assert 'fasthep-flow = {version = "==2026.10.1"}' in updated


def test_pixi_pins_rewritten_string_form() -> None:
    text = '[feature.released.pypi-dependencies]\nfasthep-distributed = ">=2026.08.1"\n'

    updated = _update_pixi_pins_text(text, {"fasthep-distributed": "2026.10.1"})

    assert 'fasthep-distributed = "==2026.10.1"' in updated


def test_pixi_pins_rewritten_case_insensitively() -> None:
    text = '[feature.released.pypi-dependencies]\nFasthep-Flow = ">=2026.08.3"\n'

    updated = _update_pixi_pins_text(text, {"fasthep-flow": "2026.10.1"})

    assert 'Fasthep-Flow = "==2026.10.1"' in updated


def test_pixi_pins_only_rewritten_inside_released_section() -> None:
    text = (
        "[pypi-dependencies]\n"
        'fasthep-flow = "*"\n'
        "[feature.released.pypi-dependencies]\n"
        'fasthep-flow = ">=2026.08.1"\n'
    )

    updated = _update_pixi_pins_text(text, {"fasthep-flow": "2026.10.1"})

    assert 'fasthep-flow = "*"' in updated
    assert 'fasthep-flow = "==2026.10.1"' in updated


def test_pixi_pins_leaves_unknown_entries_unchanged() -> None:
    text = '[feature.released.pypi-dependencies]\nuproot-browser = "*"\n'

    updated = _update_pixi_pins_text(text, {"fasthep-flow": "2026.10.1"})

    assert updated == text


def test_dry_run_reports_dependency_changes_without_mutating(tmp_path: Path) -> None:
    release_file = tmp_path / "releases.json"
    release_file.write_text(
        json.dumps(
            {
                "packages": {
                    "flow": {"dist": "fasthep-flow", "version": "2026.06.1"},
                    "workshop": {"dist": "fasthep-workshop", "version": "2026.06.1"},
                },
                "order": ["workshop"],
            }
        ),
        encoding="utf-8",
    )
    package_dir = tmp_path / "workshop"
    package_dir.mkdir()
    pyproject = package_dir / "pyproject.toml"
    original = """
[project]
name = "fasthep-workshop"
dynamic = ["version"]
dependencies = [
    "fasthep-flow",
]
"""
    pyproject.write_text(original, encoding="utf-8")

    script = Path(__file__).parents[1] / "update_versions.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(release_file),
            "--package",
            "workshop",
            "--dry-run",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Would update" in result.stdout
    assert pyproject.read_text(encoding="utf-8") == original


def test_dry_run_rewrites_workshop_pixi_toml(tmp_path: Path) -> None:
    release_file = tmp_path / "releases.json"
    release_file.write_text(
        json.dumps(
            {
                "packages": {
                    "flow": {"dist": "fasthep-flow", "version": "2026.10.1"},
                    "workshop": {"dist": "fasthep-workshop", "version": "2026.10.1"},
                },
                "order": ["flow", "workshop"],
            }
        ),
        encoding="utf-8",
    )
    workshop_dir = tmp_path / "workshop"
    workshop_dir.mkdir()
    pyproject = workshop_dir / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "fasthep-workshop"\ndynamic = ["version"]\ndependencies = []\n',
        encoding="utf-8",
    )
    pixi_toml = workshop_dir / "pixi.toml"
    original = (
        "[feature.released.pypi-dependencies]\n"
        'fasthep-flow = {version = ">=2026.08.3"}\n'
    )
    pixi_toml.write_text(original, encoding="utf-8")

    script = Path(__file__).parents[1] / "update_versions.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(release_file),
            "--package",
            "workshop",
            "--dry-run",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Would update" in result.stdout
    assert "pixi.toml" in result.stdout
    assert pixi_toml.read_text(encoding="utf-8") == original
