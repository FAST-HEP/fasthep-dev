from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "print_release_plan.py"


def _write_pyproject(path: Path, *, name: str, version: str, deps: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    deps_text = ",\n".join(f'    "{dep}"' for dep in deps)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\ndependencies = [\n{deps_text}\n]\n',
        encoding="utf-8",
    )


def test_print_release_plan_uses_fasthep_version_as_release_label(tmp_path):
    _write_pyproject(tmp_path / "toolbench", name="fasthep-toolbench", version="2026.10.1", deps=[])
    release_file = tmp_path / "releases.json"
    release_file.write_text(
        json.dumps(
            {
                "packages": {
                    "toolbench": {"dist": "fasthep-toolbench", "version": "2026.10.1"},
                    "fasthep": {"dist": "fasthep", "version": "2026.10.1"},
                },
                "order": ["toolbench", "fasthep"],
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(release_file)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Release: 2026.10.1" in result.stdout


def test_print_release_plan_fails_on_bad_order(tmp_path):
    _write_pyproject(tmp_path / "flow", name="fasthep-flow", version="2026.10.1", deps=["fasthep-toolbench"])
    _write_pyproject(tmp_path / "toolbench", name="fasthep-toolbench", version="2026.10.1", deps=[])
    release_file = tmp_path / "releases.json"
    release_file.write_text(
        json.dumps(
            {
                "packages": {
                    "flow": {"dist": "fasthep-flow", "version": "2026.10.1"},
                    "toolbench": {"dist": "fasthep-toolbench", "version": "2026.10.1"},
                },
                "order": ["flow", "toolbench"],
            }
        )
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(release_file)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
