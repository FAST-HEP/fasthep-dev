from __future__ import annotations

import json

import pytest

from scripts.release.release_data import PackageSpec, load_release_plan


def test_load_release_plan_reads_dist_and_version(tmp_path):
    path = tmp_path / "releases.json"
    path.write_text(
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

    plan = load_release_plan(path)

    assert plan.packages["toolbench"] == PackageSpec(dist="fasthep-toolbench", version="2026.10.1")
    assert plan.order == ["toolbench", "fasthep"]
    assert plan.release_version == "2026.10.1"


def test_load_release_plan_rejects_unknown_order_key(tmp_path):
    path = tmp_path / "releases.json"
    path.write_text(
        json.dumps(
            {
                "packages": {"flow": {"dist": "fasthep-flow", "version": "2026.10.1"}},
                "order": ["flow", "distributed"],
            }
        )
    )

    with pytest.raises(SystemExit, match="distributed"):
        load_release_plan(path)


def test_load_release_plan_rejects_missing_dist_or_version(tmp_path):
    path = tmp_path / "releases.json"
    path.write_text(
        json.dumps(
            {
                "packages": {"flow": {"dist": "fasthep-flow"}},
                "order": ["flow"],
            }
        )
    )

    with pytest.raises(SystemExit):
        load_release_plan(path)
