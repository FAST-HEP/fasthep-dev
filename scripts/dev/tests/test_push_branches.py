from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.dev import push_branches


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def stack(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    _git("init", "-q", "--bare", str(remote), cwd=tmp_path)
    repo = tmp_path / "work" / "pkg"
    repo.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@example.org", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    (repo / "a").write_text("a")
    _git("add", "a", cwd=repo)
    _git("commit", "-q", "-m", "first", cwd=repo)
    _git("branch", "feat/x", cwd=repo)
    manifest = tmp_path / "work" / "push.yaml"
    manifest.write_text(yaml.safe_dump({"branches": [{"repo": "pkg", "branch": "feat/x"}]}))
    return tmp_path / "work"


def test_dry_run_reports_new_branch_and_pushes_nothing(stack: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert push_branches.main(["--root", str(stack), "--manifest", "push.yaml"]) == 0

    out = capsys.readouterr().out
    assert "new branch" in out and "git -C pkg push -u origin feat/x" in out
    remote = subprocess.run(["git", "ls-remote", "--heads", "origin", "feat/x"], cwd=stack / "pkg",
                            capture_output=True, text=True, check=True).stdout
    assert remote == ""


def test_execute_refuses_without_a_terminal(stack: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert push_branches.main(["--root", str(stack), "--manifest", "push.yaml", "--execute"]) == 2


def _terminal(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)


def test_there_is_no_option_to_skip_the_confirmation(stack: Path) -> None:
    with pytest.raises(SystemExit):
        push_branches.main(["--root", str(stack), "--manifest", "push.yaml", "--execute", "--yes"])


def test_wrong_confirmation_pushes_nothing(stack: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _terminal(monkeypatch, "yes")

    assert push_branches.main(["--root", str(stack), "--manifest", "push.yaml", "--execute"]) == 1


def test_confirmed_push_works_and_never_forces(
    stack: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _terminal(monkeypatch, "push")
    assert push_branches.main(["--root", str(stack), "--manifest", "push.yaml", "--execute"]) == 0
    assert push_branches.main(["--root", str(stack), "--manifest", "push.yaml"]) == 0
    assert "up to date" in capsys.readouterr().out

    # diverge: rewrite the local branch, the remote keeps the old tip
    repo = stack / "pkg"
    _git("checkout", "-q", "feat/x", cwd=repo)
    _git("commit", "-q", "--amend", "-m", "rewritten", cwd=repo)
    assert push_branches.main(["--root", str(stack), "--manifest", "push.yaml", "--execute"]) == 0
    assert "DIVERGED" in capsys.readouterr().out
