"""Tests for the changelog step, the tag guard and the release backfill.

The shared tool (FAST-HEP/.github) is replaced by a small stub so these run anywhere; the tool has
its own tests in its repository.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.release import backfill_releases, release_changelog
from scripts.release.changelog_tools import ToolFailure, check_contract, draft_section
from scripts.release.release_data import PackageSpec, ReleasePlan
from scripts.release.tag_packages import PackageTag, _require_changelog_contract

STUB = '''\
import sys
from pathlib import Path

cmd, *rest = sys.argv[1:]
if cmd == "check":
    path, version = rest
    ok = f"## [{version}]" in Path(path).read_text()
    print("" if ok else f"no `## [{version}]` section", file=sys.stderr)
    sys.exit(0 if ok else 1)
if cmd == "draft":
    if Path("NOVISIBLE").exists():
        print("no visible commits since the last tag", file=sys.stderr)
        sys.exit(2)
    print(f"## [{rest[0]}] - 2026-12-01\\n\\n### Added\\n\\n- Something new.")
    sys.exit(0)
if cmd == "insert":
    path, version = rest[0], rest[1]
    section = sys.stdin.read().strip()
    text = Path(path).read_text().replace("## [Unreleased]\\n", f"## [Unreleased]\\n\\n{section}\\n", 1)
    Path(path).write_text(text)
    sys.exit(0)
if cmd == "release-notes":
    path, version = rest[0], rest[1]
    if f"## [{version}]" not in Path(path).read_text():
        print(f"no `## [{version}]` section", file=sys.stderr)
        sys.exit(2)
    print(f"notes for {version}")
    sys.exit(0)
sys.exit(3)
'''

BASE_CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n## [2026.11.1] - 2026-11-02\n\n- Old.\n"


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    (tools / "scripts").mkdir(parents=True)
    (tools / "scripts" / "fasthep_changelog.py").write_text(STUB)
    monkeypatch.setenv("FASTHEP_DOTGITHUB", str(tools))
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def make_repo(root: Path, key: str, *, tag: str | None, changelog: str = BASE_CHANGELOG) -> Path:
    repo = root / key
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "remote", "add", "origin", f"git@github.com:FAST-HEP/fasthep-{key}.git")
    (repo / "CHANGELOG.md").write_text(changelog)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat: start")
    if tag:
        git(repo, "tag", tag)
    return repo


def plan_of(**versions: str) -> ReleasePlan:
    packages = {k: PackageSpec(dist=f"fasthep-{k}", version=v) for k, v in versions.items()}
    return ReleasePlan(packages=packages, order=list(versions))


# --- changelog_tools -------------------------------------------------------------------------


def test_missing_tool_explains_how_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTHEP_DOTGITHUB", str(tmp_path / "nowhere"))
    (tmp_path / "CHANGELOG.md").write_text(BASE_CHANGELOG)
    with pytest.raises(SystemExit, match="git submodule update"):
        check_contract(tmp_path, tmp_path / "CHANGELOG.md", "1")


def test_check_contract_and_draft_failures(workspace):
    repo = make_repo(workspace, "flow", tag=None)
    assert check_contract(workspace, repo / "CHANGELOG.md", "2026.11.1") == []
    assert check_contract(workspace, repo / "CHANGELOG.md", "2026.12.1")
    assert check_contract(workspace, repo / "missing.md", "2026.12.1")
    (repo / "NOVISIBLE").write_text("")
    with pytest.raises(ToolFailure, match="no visible commits"):
        draft_section(workspace, repo, "2026.12.1")


# --- release-changelog -----------------------------------------------------------------------


def test_write_dry_run_changes_nothing(workspace, capsys):
    make_repo(workspace, "toolbench", tag="2026.11.1")
    flow = make_repo(workspace, "flow", tag=None)
    plan = plan_of(toolbench="2026.11.1", flow="2026.12.1", fasthep="2026.12.1")
    assert release_changelog.cmd_write(workspace, plan, write=False) == 0
    out = capsys.readouterr().out
    assert "toolbench: stays at 2026.11.1" in out
    assert "=== flow 2026.12.1" in out and "- Something new." in out
    assert flow.joinpath("CHANGELOG.md").read_text() == BASE_CHANGELOG
    assert not list(flow.glob("*.fasthep-new"))


def test_write_inserts_and_commits_locally(workspace):
    flow = make_repo(workspace, "flow", tag=None)
    plan = plan_of(flow="2026.12.1", fasthep="2026.12.1")
    assert release_changelog.cmd_write(workspace, plan, write=True) == 0
    assert "## [2026.12.1]" in (flow / "CHANGELOG.md").read_text()
    assert git(flow, "log", "-1", "--format=%s") == "docs(changelog): add 2026.12.1 release\n"
    assert git(flow, "status", "--short") == ""


def test_write_writes_nothing_if_one_package_has_no_visible_commits(workspace, capsys):
    flow = make_repo(workspace, "flow", tag=None)
    render = make_repo(workspace, "render", tag=None)
    (render / "NOVISIBLE").write_text("")
    plan = plan_of(flow="2026.12.1", render="2026.12.1", fasthep="2026.12.1")
    assert release_changelog.cmd_write(workspace, plan, write=True) == 1
    assert "render:" in capsys.readouterr().err
    assert (flow / "CHANGELOG.md").read_text() == BASE_CHANGELOG


def test_tagged_package_with_visible_commits_gets_a_hint(workspace, capsys):
    make_repo(workspace, "flow", tag="2026.11.1")
    plan = plan_of(flow="2026.11.1", fasthep="2026.11.1")
    release_changelog.cmd_write(workspace, plan, write=False)
    assert "bump flow in releases.json" in capsys.readouterr().out


def test_check_reports_each_package(workspace, capsys):
    make_repo(workspace, "flow", tag=None)
    make_repo(workspace, "render", tag=None)
    plan = plan_of(flow="2026.11.1", render="2026.12.1")
    assert release_changelog.cmd_check(workspace, plan) == 1
    out = capsys.readouterr().out
    assert "ok   flow" in out and "FAIL render" in out


# --- tag guard -------------------------------------------------------------------------------


def test_tag_guard_blocks_missing_section_and_skips_tagged(workspace):
    repo = make_repo(workspace, "flow", tag=None)
    tagged = make_repo(workspace, "render", tag="2026.12.1", changelog="# Changelog\n")
    items = [
        PackageTag("flow", repo, "fasthep-flow", "2026.12.1"),
        PackageTag("render", tagged, "fasthep-render", "2026.12.1"),
    ]
    with pytest.raises(SystemExit) as exc:
        _require_changelog_contract(workspace, items)
    assert "flow: no `## [2026.12.1]` section" in str(exc.value)
    assert "render" not in str(exc.value)


def test_tag_guard_passes_when_sections_exist(workspace):
    repo = make_repo(workspace, "flow", tag=None)
    _require_changelog_contract(workspace, [PackageTag("flow", repo, "fasthep-flow", "2026.11.1")])


# --- backfill --------------------------------------------------------------------------------


@pytest.fixture
def fake_gh(workspace, monkeypatch):
    """A `gh` that lists the releases in $FAKE_GH_RELEASES and logs `release create` calls."""
    bindir = workspace.parent / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['release', 'list']:\n"
        "    print(json.dumps([{'tagName': t} for t in os.environ.get('FAKE_GH_RELEASES', '').split()]))\n"
        "elif args[:2] == ['release', 'create']:\n"
        "    open(os.environ['FAKE_GH_LOG'], 'a').write(' '.join(args) + '\\n')\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    log = workspace.parent / "gh.log"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    return log


def backfill_workspace(root: Path) -> Path:
    changelog = "# Changelog\n\n## [Unreleased]\n\n## [2026.11.1] - 2026-11-02\n\n- A.\n\n## [2026.10.1] - 2026-10-26\n\n- B.\n"
    repo = make_repo(root, "flow", tag="2026.09.1", changelog=changelog)
    for tag in ("2026.10.1", "2026.10.2", "2026.11.1"):
        git(repo, "tag", tag)
    (root / "releases.json").write_text(
        json.dumps({"packages": {"flow": {"dist": "fasthep-flow", "version": "2026.11.1"}}, "order": ["flow"]})
    )
    return repo


def test_backfill_plan_classifies_tags(workspace, fake_gh, monkeypatch, capsys):
    backfill_workspace(workspace)
    monkeypatch.setenv("FAKE_GH_RELEASES", "2026.10.1")
    items = backfill_releases.plan_items(workspace, Path("releases.json"), "2026.10.0", None)
    assert [(i.tag, i.action) for i in items] == [
        ("2026.10.1", "exists"),
        ("2026.10.2", "no-section"),  # tagged, but the changelog has no such section
        ("2026.11.1", "create"),
    ]
    assert items[-1].latest and items[-1].slug == "FAST-HEP/fasthep-flow"


def test_backfill_dry_run_and_non_terminal_refusal(workspace, fake_gh, monkeypatch):
    backfill_workspace(workspace)
    monkeypatch.setattr(sys, "argv", ["backfill", "releases.json"])
    assert backfill_releases.main() == 0
    assert not fake_gh.exists()
    monkeypatch.setattr(sys, "argv", ["backfill", "releases.json", "--execute"])
    assert backfill_releases.main() == 2  # pytest has no terminal on stdin
    assert not fake_gh.exists()


def test_backfill_execute_needs_the_typed_word_and_marks_only_the_newest_latest(
    workspace, fake_gh, monkeypatch
):
    repo = backfill_workspace(workspace)
    git(repo, "tag", "2026.12.1")
    (repo / "CHANGELOG.md").write_text(
        (repo / "CHANGELOG.md").read_text().replace("## [2026.11.1]", "## [2026.12.1] - 2026-12-01\n\n- C.\n\n## [2026.11.1]")
    )
    monkeypatch.setattr(sys, "argv", ["backfill", "releases.json", "--execute"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "nope")
    assert backfill_releases.main() == 1
    assert not fake_gh.exists()
    monkeypatch.setattr("builtins.input", lambda _: "release")
    assert backfill_releases.main() == 0
    lines = fake_gh.read_text().splitlines()
    assert len(lines) == 3  # 2026.10.1, 2026.11.1, 2026.12.1; 2026.10.2 has no section
    assert all("--verify-tag" in line for line in lines)
    assert [("--latest=true" in line) for line in lines] == [False, False, True]
