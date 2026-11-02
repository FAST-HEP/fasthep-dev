from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "validate_release.sh"

DATA = [
    "data/CMS/Zmumu/data.root",
    "data/CMS/L1Trigger/2k.root",
    "data/CMS/L1Trigger/2kmu.root",
    "data/LZ/mssi/SS_skim_Th232-late_HVInnerCone.root",
]
TUTORIALS = [
    "01-read-data/01-root-files",
    "01-read-data/03-remote-data",
    "02-transform-data/01-derived-columns",
    "06-organise-workflows/02-needs",
    "07-scale-execution/01-dask",  # outside the 01 to 06 range
]


def _workshop(tmp_path: Path, *, with_data: bool = True) -> Path:
    ws = tmp_path / "workshop"
    for t in TUTORIALS:
        (ws / "tutorials" / t).mkdir(parents=True)
        (ws / "tutorials" / t / "workflow.yaml").write_text("version: 1.0\n", encoding="utf-8")
    if with_data:
        for f in DATA:
            (ws / f).parent.mkdir(parents=True, exist_ok=True)
            (ws / f).write_text("x", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "x", "-q"],
        cwd=ws,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "tag", "-a", "2026.11.1", "-m", "r"],
        cwd=ws,
        check=True,
    )
    return ws


def _fake_pixi(tmp_path: Path, *, fail_on: str = "") -> dict[str, str]:
    """A `pixi` that records its arguments and fails for workflows containing `fail_on`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "pixi"
    fake.write_text(
        '#!/usr/bin/env bash\n'
        f'echo "$PWD $*" >> "{tmp_path}/pixi-calls.txt"\n'
        f'[[ -n "{fail_on}" && "$*" == *"{fail_on}"* ]] && exit 1\n'
        'exit 0\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}


def _run(tmp_path: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--workshop", str(tmp_path / "workshop"), *args],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_dry_run_lists_commands_runs_nothing_and_uses_the_latest_tag(tmp_path: Path) -> None:
    _workshop(tmp_path)
    env = _fake_pixi(tmp_path)

    result = _run(tmp_path, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "release 2026.11.1" in result.stdout
    assert "--outdir=build/2026.11.1-CMS-Zmumu" in result.stdout
    assert "examples/CMS/L1Trigger/workflow.yaml --outdir=build/2026.11.1-CMS-L1Trigger" in result.stdout
    assert "examples/LZ/mssi/workflow.yaml --outdir=build/2026.11.1-LZ-mssi" in result.stdout
    assert not (tmp_path / "pixi-calls.txt").exists()
    assert not (tmp_path / "workshop" / "build").exists()


def test_tutorials_are_limited_to_sections_01_to_06_and_skip_the_remote_one(tmp_path: Path) -> None:
    _workshop(tmp_path)
    env = _fake_pixi(tmp_path)

    result = _run(tmp_path, env)

    assert "tutorials/01-read-data/01-root-files/workflow.yaml" in result.stdout
    assert "tutorials/06-organise-workflows/02-needs/workflow.yaml" in result.stdout
    assert "skipping 01-read-data/03-remote-data" in result.stdout
    assert "03-remote-data/workflow.yaml" not in result.stdout
    assert "07-scale-execution" not in result.stdout


def test_run_executes_in_the_workshop_directory_and_fails_if_any_run_fails(tmp_path: Path) -> None:
    ws = _workshop(tmp_path)
    env = _fake_pixi(tmp_path, fail_on="LZ/mssi")

    result = _run(tmp_path, env, "--run")

    assert result.returncode == 1, result.stdout + result.stderr
    calls = (tmp_path / "pixi-calls.txt").read_text(encoding="utf-8").splitlines()
    assert len(calls) == 3 + 3  # three examples and three tutorials in range, one skipped
    assert all(line.startswith(str(ws.resolve())) for line in calls)  # cwd is workshop/
    summary = (ws / "build" / "2026.11.1-validation" / "summary.txt").read_text(encoding="utf-8")
    assert "1 example-LZ-mssi" in summary
    assert "0 example-CMS-Zmumu" in summary
    assert "1 run(s) failed" in result.stdout


def test_run_stops_before_running_anything_when_input_data_is_missing(tmp_path: Path) -> None:
    _workshop(tmp_path, with_data=False)
    env = _fake_pixi(tmp_path)

    result = _run(tmp_path, env, "--run")

    assert result.returncode == 2
    assert "MISSING:" in result.stdout and "2kmu.root" in result.stdout
    assert not (tmp_path / "pixi-calls.txt").exists()


def test_dry_run_reports_missing_data_without_failing(tmp_path: Path) -> None:
    _workshop(tmp_path, with_data=False)
    env = _fake_pixi(tmp_path)

    result = _run(tmp_path, env)

    assert result.returncode == 0
    assert "MISSING:" in result.stdout
