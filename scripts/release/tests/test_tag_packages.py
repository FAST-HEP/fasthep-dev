from __future__ import annotations

from pathlib import Path

from scripts.release.tag_packages import PackageTag


def test_package_tag_uses_plain_version_tag() -> None:
    item = PackageTag(key="flow", path=Path("flow"), version="2026.06.1")

    assert item.tag == "2026.06.1"
    assert item.tag != "fasthep-flow-v2026.06.1"


def test_package_tag_message_keeps_distribution_name() -> None:
    item = PackageTag(key="flow", path=Path("flow"), version="2026.06.1")

    assert item.message == "Release fasthep-flow 2026.06.1"
