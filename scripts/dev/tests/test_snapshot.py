from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.dev import snapshot


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "MODULES", {"flow": "hepflow", "fasthep": "fasthep"})
    root = tmp_path / "workspace with spaces"
    for name, module in snapshot.MODULES.items():
        remote = tmp_path / f"{name}.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
        repo = root / name
        source = repo / "src" / module
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("")
        (source / "_version.pyi").write_text("# tracked stub\n")
        (repo / ".gitignore").write_text("_version.py\n")
        (repo / "pyproject.toml").write_text(
            "[tool.hatch.build.hooks.vcs]\n"
            f'version-file = "src/{module}/_version.py"\n'
            '[tool.hatch.version.raw-options]\nfallback_version = "2026.06.1"\n'
        )
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.name", "Test")
        git(repo, "config", "user.email", "test@example.org")
        git(repo, "remote", "add", "origin", str(remote))
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "initial")
        if name == "flow":
            git(repo, "tag", "2026.11.1")
        git(repo, "push", "-q", "origin", "main", "--tags")
    return root


@pytest.mark.parametrize(
    ("describe", "version"),
    [
        ("2026.11.1", "2026.11.1"),
        ("2026.11.1-0-gf48a993", "2026.11.1"),
        ("2026.11.1-75-gf48a993", "2026.11.2.dev75+gf48a993"),
    ],
)
def test_guess_version(describe, version):
    assert snapshot.guess_version(describe) == version


def invoke(root, *args):
    common = ["--root", str(root)]
    if args and args[0] in ("env", "run"):
        return snapshot.main([args[0], *common, *args[1:]])
    return snapshot.main([*common, "--no-fetch", *args])


def test_create_current_and_refresh(workspace, capsys):
    path = workspace / "build/worktrees/snapshot-flow"
    assert invoke(workspace) == 0
    assert not path.exists()
    assert "create" in capsys.readouterr().out
    assert invoke(workspace, "--execute") == 0
    version = path / "src/hepflow/_version.py"
    assert "__version__ = version = '2026.11.1'" in version.read_text()
    assert version.with_suffix(".pyi").read_text() == "# tracked stub\n"
    fallback = path.parent / "snapshot-fasthep/src/fasthep/_version.py"
    assert "2026.06.1" in fallback.read_text()
    stamp = version.stat().st_mtime_ns
    capsys.readouterr()
    assert invoke(workspace, "--execute") == 0
    assert "current" in capsys.readouterr().out
    assert version.stat().st_mtime_ns == stamp

    repo = workspace / "flow"
    git(repo, "commit", "--allow-empty", "-qm", "advance")
    git(repo, "push", "-q", "origin", "main")
    assert invoke(workspace, "--execute") == 0
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")
    assert "2026.11.2.dev1+g" in version.read_text()


def test_dirty_skip_and_override(workspace, capsys):
    repo = workspace / "flow"
    git(repo, "branch", "topic")
    git(repo, "commit", "--allow-empty", "-qm", "advance")
    git(repo, "push", "-q", "origin", "main")
    assert invoke(workspace, "--execute", "--repo", "flow", "--use", "flow=topic") == 0
    path = workspace / "build/worktrees/snapshot-flow"
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "topic")
    assert git(path, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert invoke(workspace, "--repo", "flow") == 0
    assert "moves from override" in capsys.readouterr().out

    dirty = path / "notes"
    dirty.write_text("keep me")
    assert invoke(workspace, "--execute", "--repo", "flow") == 0
    assert "skip: dirty" in capsys.readouterr().out
    assert dirty.read_text() == "keep me"
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "topic")
    dirty.unlink()
    assert invoke(workspace, "--execute", "--repo", "flow") == 0
    assert git(path, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")


def test_failures_are_reported_per_repo(workspace, capsys):
    path = workspace / "build/worktrees/snapshot-flow"
    path.mkdir(parents=True)
    sentinel = path / "keep"
    sentinel.write_text("keep")
    assert invoke(workspace, "--execute") == 1
    assert "fail:" in capsys.readouterr().out
    assert sentinel.read_text() == "keep"
    assert (path.parent / "snapshot-fasthep/.git").is_file()
    git(workspace / "fasthep", "update-ref", "-d", "refs/remotes/origin/main")
    assert invoke(workspace, "--repo", "fasthep") == 1
    assert "origin/main" in capsys.readouterr().out


def test_env_and_freshness(workspace, capsys):
    assert invoke(workspace, "--execute", "--repo", "flow") == 0
    capsys.readouterr()
    assert invoke(workspace, "env") == 1
    assert "missing snapshot" in capsys.readouterr().err
    assert invoke(workspace, "env", "--repo", "flow") == 0
    shell = capsys.readouterr()
    assert shell.out.startswith("export PYTHONPATH=")
    assert '"$PATH"' in shell.out
    assert "flow: snapshot" in shell.err
    assert "fasthep: workspace checkout" in shell.err
    assert invoke(workspace, "env", "--repo", "flow", "--json") == 0
    env = json.loads(capsys.readouterr().out)
    paths = env["PYTHONPATH"].split(":")
    assert paths[:2] == [
        str(workspace / "build/worktrees/snapshot-flow/src"),
        str(workspace / "fasthep/src"),
    ]

    repo = workspace / "flow"
    git(repo, "commit", "--allow-empty", "-qm", "advance")
    git(repo, "push", "-q", "origin", "main")
    assert invoke(workspace, "env", "--repo", "flow") == 0
    assert "1 behind" in capsys.readouterr().err
    assert invoke(workspace, "env", "--repo", "flow", "--require-fresh") == 1
    assert capsys.readouterr().out == ""


def test_run_refuses_wrong_import_then_executes(workspace, capfd, monkeypatch):
    assert invoke(workspace, "--execute", "--repo", "flow") == 0
    bin_dir = workspace / ".pixi/envs/dev/bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to(sys.executable)
    source = workspace / "build/worktrees/snapshot-flow/src/hepflow"
    (source / "__init__.py").write_text(
        f"__file__ = {str(workspace / 'elsewhere.py')!r}"
    )
    calls = []
    monkeypatch.setattr(snapshot.os, "execvpe", lambda *args: calls.append(args))
    args = ("run", "--repo", "flow", "--", "python", "-V")
    assert invoke(workspace, *args) == 1
    assert "outside" in capfd.readouterr().err
    assert not calls
    (source / "__init__.py").write_text("")
    monkeypatch.chdir(workspace)
    assert invoke(workspace, *args) == 0
    assert calls[0][1] == ["python", "-V"]
    assert str(source / "__init__.py") in capfd.readouterr().err


def test_preserve_existing_ignored_version(workspace, capsys):
    assert invoke(workspace, "--execute", "--repo", "flow") == 0
    path = workspace / "build/worktrees/snapshot-flow/src/hepflow/_version.py"
    path.write_text("# local version file\n")
    assert invoke(workspace, "--execute", "--repo", "flow") == 1
    assert "refusing to overwrite" in capsys.readouterr().out
    assert path.read_text() == "# local version file\n"


def test_run_checks_cwd_and_accepts_pixi_forwarding(workspace, capfd, monkeypatch):
    assert invoke(workspace, "--execute", "--repo", "flow") == 0
    bin_dir = workspace / ".pixi/envs/dev/bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to(sys.executable)
    (workspace / "hepflow.py").write_text("")
    monkeypatch.delenv("PYTHONSAFEPATH", raising=False)
    assert invoke(workspace, "run", "--repo", "flow", "python", "-V") == 1
    assert "hepflow.py resolves outside" in capfd.readouterr().err


def test_dest_places_snapshots_and_env_finds_them(workspace, capsys):
    dest = workspace / "build/review"
    assert invoke(workspace, "--dest", "build/review", "--execute") == 0
    assert (dest / "flow/.git").is_file()
    assert (dest / "fasthep/.git").is_file()
    assert not (workspace / "build/worktrees").exists()
    capsys.readouterr()
    assert invoke(workspace, "env", "--dest", "build/review", "--json") == 0
    assert str(dest / "flow/src") in json.loads(capsys.readouterr().out)["PYTHONPATH"]


@pytest.mark.parametrize("dest", ["build", "elsewhere", "../outside", "build/../x"])
def test_dest_must_be_below_build(workspace, dest):
    with pytest.raises(SystemExit):
        invoke(workspace, "--dest", dest)


def test_dest_refuses_non_snapshot_directory(workspace, capsys):
    (workspace / "build/review/flow").mkdir(parents=True)
    assert invoke(workspace, "--dest", "build/review", "--execute") == 1
    assert "not a worktree of flow" in capsys.readouterr().out
