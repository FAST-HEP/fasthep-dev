from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from scripts.release.release_data import PackageSpec, ReleasePlan
from scripts.release.tag_packages import PackageTag, _selected_tags


def test_package_tag_uses_plain_version_tag() -> None:
    item = PackageTag(key="flow", path=Path("flow"), dist="fasthep-flow", version="2026.06.1")

    assert item.tag == "2026.06.1"
    assert item.tag != "fasthep-flow-v2026.06.1"


def test_package_tag_message_keeps_distribution_name() -> None:
    item = PackageTag(key="flow", path=Path("flow"), dist="fasthep-flow", version="2026.06.1")

    assert item.message == "Release fasthep-flow 2026.06.1"


def _plan() -> ReleasePlan:
    packages = {
        key: PackageSpec(dist=f"fasthep-{key}" if key != "fasthep" else "fasthep", version="2026.10.1")
        for key in ("toolbench", "flow", "workshop", "fasthep")
    }
    return ReleasePlan(packages=packages, order=["toolbench", "flow", "workshop", "fasthep"])


def test_default_batch_excludes_workshop_and_fasthep(tmp_path: Path) -> None:
    plan = _plan()

    keys = [item.key for item in _selected_tags(root=tmp_path, plan=plan, package=None)]

    assert keys == ["toolbench", "flow"]


def test_explicit_package_workshop_is_selected_alone(tmp_path: Path) -> None:
    plan = _plan()

    keys = [item.key for item in _selected_tags(root=tmp_path, plan=plan, package="workshop")]

    assert keys == ["workshop"]


def test_explicit_package_fasthep_is_selected_alone(tmp_path: Path) -> None:
    plan = _plan()

    keys = [item.key for item in _selected_tags(root=tmp_path, plan=plan, package="fasthep")]

    assert keys == ["fasthep"]


def test_creating_a_tag_touches_pyproject_to_bust_stale_editable_version_cache(
    tmp_path: Path,
) -> None:
    # pixi/uv cache an editable package's hatch-vcs version by pyproject.toml's
    # mtime, not by git state, so a bare `git tag` leaves `pixi run` resolving
    # the pre-tag dev-snapshot version forever. Touching pyproject.toml after
    # tagging busts that cache.
    package_dir = tmp_path / "toolbench"
    package_dir.mkdir()
    pyproject = package_dir / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "fasthep-toolbench"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=package_dir, check=True)
    subprocess.run(["git", "add", "-A"], cwd=package_dir, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "x", "-q"],
        cwd=package_dir,
        check=True,
    )
    stale_mtime = time.time() - 3600
    os.utime(pyproject, (stale_mtime, stale_mtime))

    release_file = tmp_path / "releases.json"
    release_file.write_text(
        json.dumps(
            {
                "packages": {"toolbench": {"dist": "fasthep-toolbench", "version": "2026.10.1"}},
                "order": ["toolbench"],
            }
        ),
        encoding="utf-8",
    )

    script = Path(__file__).parents[1] / "tag_packages.py"
    result = subprocess.run(
        [sys.executable, str(script), str(release_file), "--package", "toolbench"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert pyproject.stat().st_mtime > stale_mtime
