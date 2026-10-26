from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "check_release.py"


def _write_pyproject(path: Path, *, name: str, version: str, deps: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    deps_text = ",\n".join(f'    "{dep}"' for dep in deps)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\ndependencies = [\n{deps_text}\n]\n',
        encoding="utf-8",
    )


def test_check_release_reports_order_and_version_errors(tmp_path):
    # toolbench depends on nothing; flow (wrongly placed before toolbench) depends on it
    _write_pyproject(tmp_path / "toolbench", name="fasthep-toolbench", version="2026.10.1", deps=[])
    _write_pyproject(tmp_path / "flow", name="fasthep-flow", version="2026.10.1", deps=["fasthep-toolbench"])
    for path in (tmp_path / "toolbench", tmp_path / "flow"):
        subprocess.run(["git", "init", "-q"], cwd=path, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "x", "-q"],
            cwd=path,
            check=True,
        )
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

    assert result.returncode == 1, result.stdout + result.stderr
    assert "is not earlier in the release order" in result.stdout
