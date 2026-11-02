from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.dev import sync_dependabot

TEMPLATE = "version: 2\nupdates: []\n"


def _workspace(root: Path) -> None:
    (root / "dot-github" / "templates").mkdir(parents=True)
    (root / "dot-github" / "templates" / "dependabot.yml").write_text(TEMPLATE)
    (root / "releases.json").write_text(json.dumps({"packages": {}, "order": ["same", "old", "new", "dirty"]}))
    for key in ("same", "old", "new", "dirty"):
        repo = root / key
        (repo / ".github").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (root / "same/.github/dependabot.yml").write_text(TEMPLATE)
    (root / "old/.github/dependabot.yml").write_text("version: 2\n")
    (root / "dirty/.github/dependabot.yml").write_text("version: 2\n")
    for key in ("same", "old", "dirty"):
        subprocess.run(["git", "add", "-A"], cwd=root / key, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x"],
            cwd=root / key,
            check=True,
        )
    (root / "dirty/.github/dependabot.yml").write_text("version: 2\n# local edit\n")


def test_dry_run_reports_and_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _workspace(tmp_path)

    assert sync_dependabot.main(["--root", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "same      same" in out and "different old" in out and "missing   new" in out
    assert "+updates: []" in out and "dry run" in out
    assert (tmp_path / "old/.github/dependabot.yml").read_text() == "version: 2\n"
    assert not (tmp_path / "new/.github/dependabot.yml").exists()


def test_write_updates_missing_and_different_but_refuses_uncommitted_edits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _workspace(tmp_path)

    assert sync_dependabot.main(["--root", str(tmp_path), "--write"]) == 1

    assert (tmp_path / "old/.github/dependabot.yml").read_text() == TEMPLATE
    assert (tmp_path / "new/.github/dependabot.yml").read_text() == TEMPLATE
    assert (tmp_path / "dirty/.github/dependabot.yml").read_text() == "version: 2\n# local edit\n"
    assert "uncommitted changes" in capsys.readouterr().err


def test_missing_template_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "releases.json").write_text(json.dumps({"order": []}))

    assert sync_dependabot.main(["--root", str(tmp_path)]) == 2
    assert "submodule update" in capsys.readouterr().err


def test_final_newline_only_difference_is_called_out(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _workspace(tmp_path)
    (tmp_path / "old/.github/dependabot.yml").write_text(TEMPLATE.rstrip("\n"))

    sync_dependabot.main(["--root", str(tmp_path)])

    assert "differs only in the final newline" in capsys.readouterr().out
