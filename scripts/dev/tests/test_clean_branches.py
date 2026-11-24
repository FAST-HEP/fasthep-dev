from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.dev import clean_branches


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


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
    _git("add", "a", cwd=repo)
    _git("commit", "-q", "-m", "first", cwd=repo)
    _git("push", "-q", "-u", "origin", "main", cwd=repo)
    # merged on both sides
    _git("branch", "done", cwd=repo)
    _git("push", "-q", "origin", "done", cwd=repo)
    # merged, local only
    _git("branch", "done-local", cwd=repo)
    # unmerged work, pushed
    _git("checkout", "-q", "-b", "wip", cwd=repo)
    (repo / "b").write_text("b")
    _git("add", "b", cwd=repo)
    _git("commit", "-q", "-m", "wip", cwd=repo)
    _git("push", "-q", "origin", "wip", cwd=repo)
    _git("checkout", "-q", "main", cwd=repo)
    # merged but long-lived
    _git("branch", "legacy", cwd=repo)
    # merged but checked out in a worktree
    _git("worktree", "add", "-q", "-b", "in-tree", str(tmp_path / "tree"), "main", cwd=repo)
    return root


def _run(root: Path, *extra: str, ask=input) -> int:
    return clean_branches.main(["--root", str(root), "--repo", "pkg", "--no-fetch", *extra], ask=ask)


def _states(root: Path) -> dict[str, tuple[str, str]]:
    branches = clean_branches.collect(root / "pkg", "pkg", fetch=False, prs={})
    return {b.name: (b.where, b.state) for b in branches}


def test_states_compare_with_the_default_branch(workspace: Path) -> None:
    states = _states(workspace)

    assert states["done"] == ("both", "merged")
    assert states["done-local"] == ("local", "merged")
    assert states["wip"] == ("both", "KEEP: unmerged")
    assert states["in-tree"] == ("local", "KEEP: worktree tree")
    assert "main" not in states


def test_a_merged_pr_with_the_same_tip_is_suggested_even_when_not_an_ancestor(workspace: Path) -> None:
    repo = workspace / "pkg"
    tip = _git("rev-parse", "wip", cwd=repo).strip()
    prs = {"wip": {"number": 7, "state": "merged", "sha": tip}}

    branch = next(b for b in clean_branches.collect(repo, "pkg", fetch=False, prs=prs) if b.name == "wip")

    assert (branch.state, branch.deletable, branch.squash_proven) == ("PR merged", True, True)


def test_an_open_pr_or_newer_commits_are_kept(workspace: Path) -> None:
    repo = workspace / "pkg"
    prs = {
        "wip": {"number": 7, "state": "open", "sha": "x"},
        "done": {"number": 3, "state": "merged", "sha": "other"},
    }

    states = {b.name: b.state for b in clean_branches.collect(repo, "pkg", fetch=False, prs=prs)}

    assert states["wip"] == "KEEP: open PR"
    assert states["done"] == "merged"  # ancestor wins: nothing is lost


def test_dry_run_lists_commands_and_deletes_nothing(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(workspace) == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == list(clean_branches.COLUMNS)
    assert "push origin --delete done" in out
    assert "branch -d done-local" in out
    assert "--delete wip" not in out
    assert "done" in _git("branch", cwd=workspace / "pkg")


def test_execute_refuses_without_a_terminal(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert _run(workspace, "--execute") == 2
    assert "done" in _git("branch", cwd=workspace / "pkg")


def test_execute_asks_per_branch_and_deletes_local_and_remote(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    repo = workspace / "pkg"

    assert _run(workspace, "--execute", ask=lambda prompt: "y" if " done (" in prompt else "n") == 0

    assert "done\n" not in _git("branch", cwd=repo).replace("done-local", "")
    assert "done-local" in _git("branch", cwd=repo)
    assert "refs/heads/done\n" not in _git("ls-remote", "--heads", "origin", cwd=repo)
    assert "refs/heads/wip" in _git("ls-remote", "--heads", "origin", cwd=repo)


def test_a_remote_branch_that_moved_is_not_deleted(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    repo = workspace / "pkg"
    branches = clean_branches.collect(repo, "pkg", fetch=False, prs={})
    done = next(b for b in branches if b.name == "done")
    done.remote = "0" * 40  # the listing no longer matches the remote

    assert clean_branches.delete(done) is False
    assert "refs/heads/done" in _git("ls-remote", "--heads", "origin", cwd=repo)


def test_the_token_file_is_read_without_printing_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = tmp_path / "t.env"
    file.write_text("OTHER=1\nGITHUB_TOKEN=secret-value\n")

    assert clean_branches.read_token(file) == "secret-value"
    assert capsys.readouterr().out == ""


def test_long_lived_branches_are_protected(workspace: Path) -> None:
    assert _states(workspace)["legacy"] == ("local", "KEEP: protected")


def test_protect_replaces_the_default(workspace: Path) -> None:
    branches = clean_branches.collect(workspace / "pkg", "pkg", fetch=False, prs={}, protect=("done*",))
    states = {b.name: b.state for b in branches}

    assert states["legacy"] == "merged"
    assert states["done"] == "KEEP: protected"


def test_a_prunable_worktree_does_not_protect_its_branch(workspace: Path, tmp_path: Path) -> None:
    import shutil  # noqa: PLC0415

    shutil.rmtree(tmp_path / "tree")  # the worktree folder is gone; git still lists it as prunable

    assert _states(workspace)["in-tree"] == ("local", "merged")
