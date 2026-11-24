from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.dev import clean_worktrees


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    _git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    root = tmp_path / "ws"
    repo = root / "pkg"
    repo.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "t@example.org", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    (repo / "a").write_text("a")
    (repo / ".gitignore").write_text("out/\n")
    _git("add", ".", cwd=repo)
    _git("commit", "-q", "-m", "first", cwd=repo)
    _git("push", "-q", "-u", "origin", "main", cwd=repo)
    base = root / "build" / "worktrees"
    base.mkdir(parents=True)
    # merged: branch at main
    _git("worktree", "add", "-q", "-b", "done", str(base / "pkg-done"), "origin/main", cwd=repo)
    # unpushed: one commit on no remote
    _git("worktree", "add", "-q", "-b", "wip", str(base / "pkg-wip"), "origin/main", cwd=repo)
    (base / "pkg-wip" / "b").write_text("b")
    _git("add", "b", cwd=base / "pkg-wip")
    _git("commit", "-q", "-m", "wip", cwd=base / "pkg-wip")
    # dirty + ignored files
    _git("worktree", "add", "-q", "-b", "dirty", str(base / "pkg-dirty"), "origin/main", cwd=repo)
    (base / "pkg-dirty" / "c").write_text("c")
    (base / "pkg-dirty" / "out").mkdir()
    (base / "pkg-dirty" / "out" / "x").write_text("x")
    return root


def _verdicts(root: Path) -> dict[str, str]:
    found = [clean_worktrees.inspect(p, fetch=False) for p in clean_worktrees.find_worktrees(root)]
    return {w.name: w.verdict() for w in found}


def test_verdicts_compare_with_the_remote(workspace: Path) -> None:
    assert _verdicts(workspace) == {
        "pkg-dirty": "DIRTY",
        "pkg-done": "merged",
        "pkg-wip": "UNPUSHED",
    }


def test_ignored_files_are_listed_apart_from_dirty_ones(workspace: Path) -> None:
    wt = clean_worktrees.inspect(workspace / "build" / "worktrees" / "pkg-dirty", fetch=False)

    assert wt.dirty == ["c"]
    assert wt.ignored == ["out/"]


def test_dry_run_removes_nothing(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert clean_worktrees.main(["--root", str(workspace), "--no-fetch"]) == 0

    assert (workspace / "build" / "worktrees" / "pkg-done").is_dir()
    assert "Nothing removed" in capsys.readouterr().out


def test_execute_refuses_without_a_terminal(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert clean_worktrees.main(["--root", str(workspace), "--no-fetch", "--execute"]) == 2
    assert (workspace / "build" / "worktrees" / "pkg-done").is_dir()


def test_execute_asks_per_worktree_and_unpushed_needs_its_name(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    answers = {"pkg-dirty": "n", "pkg-done": "y", "pkg-wip": "y"}  # "y" must not delete pkg-wip

    def ask(prompt: str) -> str:
        name = next(n for n in answers if n in prompt)
        return answers[name]

    assert clean_worktrees.main(["--root", str(workspace), "--no-fetch", "--execute"], ask=ask) == 0

    base = workspace / "build" / "worktrees"
    assert not (base / "pkg-done").exists()
    assert (base / "pkg-wip").is_dir()
    assert (base / "pkg-dirty").is_dir()


def test_typing_the_name_removes_an_unpushed_worktree_but_keeps_the_branch(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    assert clean_worktrees.main(
        ["--root", str(workspace), "--no-fetch", "--execute", "--only", "pkg-wip"],
        ask=lambda prompt: "pkg-wip",
    ) == 0

    assert not (workspace / "build" / "worktrees" / "pkg-wip").exists()
    branches = subprocess.run(
        ["git", "branch"], cwd=workspace / "pkg", capture_output=True, text=True, check=True
    ).stdout
    assert "wip" in branches


def test_merged_only_filters(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean_worktrees.main(["--root", str(workspace), "--no-fetch", "--merged-only"])

    out = capsys.readouterr().out
    assert "pkg-done" in out
    assert "pkg-wip" not in out


def test_list_prints_a_table_with_headers_and_a_legend(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean_worktrees.main(["--root", str(workspace), "--no-fetch"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == list(clean_worktrees.COLUMNS)
    assert set(lines[1].replace(" ", "")) == {"-"}
    done = next(line for line in lines if line.startswith("pkg-done"))
    assert done.split()[-1] == "merged"
    assert "UNPUSHED            HEAD is on no remote" in "\n".join(lines)
