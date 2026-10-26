from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.release.release_data import (
    PackageSpec,
    ReleasePlan,
    latest_tag,
    load_release_plan,
    validate_calendar_version,
    validate_order,
    validate_workshop_pins,
)


def _write_pyproject(path: Path, deps: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    deps_text = ",\n".join(f'    "{dep}"' for dep in deps)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\ndependencies = [\n{deps_text}\n]\n',
        encoding="utf-8",
    )


def _plan(dists: dict[str, str], order: list[str]) -> ReleasePlan:
    packages = {key: PackageSpec(dist=dist, version="2026.10.1") for key, dist in dists.items()}
    return ReleasePlan(packages=packages, order=order)


def _write_pixi_toml(tmp_path: Path, deps: dict[str, str]) -> None:
    workshop_dir = tmp_path / "workshop"
    workshop_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(f"{dist} = {value}" for dist, value in deps.items())
    (workshop_dir / "pixi.toml").write_text(
        f"[feature.released.pypi-dependencies]\n{lines}\n",
        encoding="utf-8",
    )


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


def test_validate_order_passes_for_correct_order(tmp_path):
    _write_pyproject(tmp_path / "flow", deps=[])
    _write_pyproject(tmp_path / "carpenter", deps=["fasthep-flow>=2026.5.0"])
    plan = _plan({"flow": "fasthep-flow", "carpenter": "fasthep-carpenter"}, order=["flow", "carpenter"])

    assert validate_order(plan, tmp_path) == []


def test_validate_order_flags_forward_dependency(tmp_path):
    _write_pyproject(tmp_path / "flow", deps=["fasthep-carpenter"])
    _write_pyproject(tmp_path / "carpenter", deps=[])
    plan = _plan({"flow": "fasthep-flow", "carpenter": "fasthep-carpenter"}, order=["flow", "carpenter"])

    errors = validate_order(plan, tmp_path)

    assert any("carpenter" in e and "flow" in e for e in errors)


def test_validate_order_flags_self_dependency(tmp_path):
    _write_pyproject(tmp_path / "flow", deps=["fasthep-flow"])
    plan = _plan({"flow": "fasthep-flow"}, order=["flow"])

    assert validate_order(plan, tmp_path) != []


def test_validate_order_ignores_extras_and_markers(tmp_path):
    _write_pyproject(tmp_path / "toolbench", deps=[])
    _write_pyproject(tmp_path / "cli", deps=["fasthep-toolbench[display,http]"])
    plan = _plan({"toolbench": "fasthep-toolbench", "cli": "fasthep-cli"}, order=["toolbench", "cli"])

    assert validate_order(plan, tmp_path) == []


def test_validate_order_is_case_insensitive(tmp_path):
    _write_pyproject(tmp_path / "toolbench", deps=[])
    _write_pyproject(tmp_path / "cli", deps=["Fasthep-Toolbench"])
    plan = _plan({"toolbench": "fasthep-toolbench", "cli": "fasthep-cli"}, order=["toolbench", "cli"])

    assert validate_order(plan, tmp_path) == []


def test_validate_order_flags_dependency_on_package_missing_from_order(tmp_path):
    # "toolbench" is a known package (in `packages`) but was left out of `order" by mistake.
    _write_pyproject(tmp_path / "cli", deps=["fasthep-toolbench"])
    plan = _plan({"cli": "fasthep-cli", "toolbench": "fasthep-toolbench"}, order=["cli"])

    errors = validate_order(plan, tmp_path)

    assert any("fasthep-toolbench" in e or "toolbench" in e for e in errors)


def test_validate_order_flags_unregistered_fasthep_dependency(tmp_path):
    _write_pyproject(tmp_path / "cli", deps=["fasthep-notarealpackage"])
    plan = _plan({"cli": "fasthep-cli"}, order=["cli"])

    errors = validate_order(plan, tmp_path)

    assert any("notarealpackage" in e.lower() or "fasthep-notarealpackage" in e for e in errors)


@pytest.mark.parametrize(
    "latest,candidate,ok",
    [
        (None, "2026.10.1", True),
        (None, "2026.10.2", False),
        ("2026.10.1", "2026.10.2", True),
        ("2026.10.1", "2026.10.3", False),  # skipped a patch
        ("2026.10.4", "2026.11.1", True),  # new month resets
        ("2026.10.4", "2026.11.2", False),  # new month must start at 1
        ("2026.10.4", "2026.09.1", False),  # goes backwards
        ("2026.10.4", "not-a-version", False),
    ],
)
def test_validate_calendar_version(latest, candidate, ok):
    errors = validate_calendar_version("flow", latest, candidate)

    assert (errors == []) is ok


def test_validate_workshop_pins_accepts_exact_pins(tmp_path):
    _write_pixi_toml(
        tmp_path,
        {
            "fasthep-flow": '{version = "==2026.10.1"}',
            "fasthep-distributed": '"==2026.10.1"',
        },
    )
    plan = _plan(
        {"flow": "fasthep-flow", "distributed": "fasthep-distributed", "workshop": "fasthep-workshop"},
        order=["flow", "distributed", "workshop"],
    )

    assert validate_workshop_pins(plan, tmp_path) == []


def test_validate_workshop_pins_rejects_floor_pin_table_form(tmp_path):
    _write_pixi_toml(tmp_path, {"fasthep-flow": '{version = ">=2026.10.1"}'})
    plan = _plan({"flow": "fasthep-flow", "workshop": "fasthep-workshop"}, order=["flow", "workshop"])

    errors = validate_workshop_pins(plan, tmp_path)

    assert any("fasthep-flow" in e for e in errors)


def test_validate_workshop_pins_rejects_floor_pin_string_form(tmp_path):
    _write_pixi_toml(tmp_path, {"fasthep-distributed": '">=2026.10.1"'})
    plan = _plan(
        {"distributed": "fasthep-distributed", "workshop": "fasthep-workshop"},
        order=["distributed", "workshop"],
    )

    errors = validate_workshop_pins(plan, tmp_path)

    assert any("fasthep-distributed" in e for e in errors)


def test_validate_workshop_pins_ignores_packages_not_listed(tmp_path):
    _write_pixi_toml(tmp_path, {})
    plan = _plan({"flow": "fasthep-flow", "workshop": "fasthep-workshop"}, order=["flow", "workshop"])

    assert validate_workshop_pins(plan, tmp_path) == []


def test_validate_workshop_pins_is_noop_when_workshop_not_in_plan(tmp_path):
    # a --package flow check-release run shouldn't fail on workshop's pixi.toml at all
    plan = _plan({"flow": "fasthep-flow", "toolbench": "fasthep-toolbench"}, order=["toolbench", "flow"])

    assert validate_workshop_pins(plan, tmp_path) == []


def test_validate_workshop_pins_is_case_insensitive(tmp_path):
    _write_pixi_toml(tmp_path, {"Fasthep-Flow": '">=2026.08.1"'})
    plan = _plan({"flow": "fasthep-flow", "workshop": "fasthep-workshop"}, order=["flow", "workshop"])

    errors = validate_workshop_pins(plan, tmp_path)

    assert any("fasthep-flow" in e.lower() for e in errors)


def test_validate_workshop_pins_rejects_non_version_pin_form(tmp_path):
    # pixi allows {path=..., editable=...} or {git=...} tables; a FAST-HEP pin in that form
    # is not an exact version pin and must be reported, not crash with KeyError.
    _write_pixi_toml(tmp_path, {"fasthep-flow": '{path = "../flow", editable = true}'})
    plan = _plan({"flow": "fasthep-flow", "workshop": "fasthep-workshop"}, order=["flow", "workshop"])

    errors = validate_workshop_pins(plan, tmp_path)

    assert any("fasthep-flow" in e for e in errors)


def _git_repo_with_tags(path: Path, tags: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "x", "-q"],
        cwd=path,
        check=True,
    )
    for tag in tags:
        subprocess.run(["git", "tag", tag], cwd=path, check=True)


def test_latest_tag_is_not_fooled_by_leading_zero_version_sort(tmp_path):
    # git's --sort=-v:refname treats "2026.5.0" as sorting above "2026.08.4" (strverscmp
    # compares the unpadded "5" against the padded "08" as a fraction) even though
    # 2026.08.4 is the later calendar version.
    _git_repo_with_tags(tmp_path, ["2026.5.0", "2026.08.4", "2026.08.3"])

    assert latest_tag(tmp_path) == "2026.08.4"
