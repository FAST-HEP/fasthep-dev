from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts.release.update_versions import _update_dependency_pins_text


VERSIONS = {
    "flow": "2026.06.1",
    "render": "2026.06.1",
    "workshop": "2026.06.1",
}


def test_project_name_is_not_rewritten() -> None:
    text = """
[project]
name = "fasthep-workshop"
dependencies = [
    "fasthep-flow",
]
"""

    updated = _update_dependency_pins_text(text, VERSIONS)
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

    updated = _update_dependency_pins_text(text, VERSIONS)
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

    updated = _update_dependency_pins_text(text, VERSIONS)
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

    updated = _update_dependency_pins_text(text, VERSIONS)
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

    updated = _update_dependency_pins_text(text, VERSIONS)
    parsed = tomllib.loads(updated)

    assert parsed["project"]["dependencies"] == [
        "fasthep-flow[docs] == 2026.06.1; python_version >= \"3.12\""
    ]


def test_dry_run_reports_dependency_changes_without_mutating(tmp_path: Path) -> None:
    release_file = tmp_path / "releases.json"
    release_file.write_text(
        json.dumps(
            {
                "release": "2026.06.1",
                "packages": {
                    "flow": "2026.06.1",
                    "workshop": "2026.06.1",
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
