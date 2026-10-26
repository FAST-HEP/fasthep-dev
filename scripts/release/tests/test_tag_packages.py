from __future__ import annotations

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
