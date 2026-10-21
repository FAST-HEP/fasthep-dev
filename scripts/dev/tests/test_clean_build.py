from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.dev import clean_build


def _make(root: Path) -> None:
    for run in ("old", "new", "kept"):
        (root / "pkg" / "build" / run).mkdir(parents=True)
        (root / "pkg" / "build" / run / "file.txt").write_text("x" * 10)
    (root / "pkg" / "build" / "kept" / "KEEP").write_text("")
    (root / "pkg" / "build" / "run.log").write_text("log")


def test_dry_run_deletes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make(tmp_path)

    assert clean_build.main(["--root", str(tmp_path), "--all"]) == 0

    assert (tmp_path / "pkg" / "build" / "old").is_dir()
    assert "would delete" in capsys.readouterr().out


def _terminal(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)


def test_execute_needs_a_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make(tmp_path)
    _terminal(monkeypatch, "delete")

    assert clean_build.main(["--root", str(tmp_path), "--execute"]) == 2
    assert (tmp_path / "pkg" / "build" / "old").is_dir()


def test_execute_refuses_without_a_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert clean_build.main(["--root", str(tmp_path), "--all", "--execute"]) == 2
    assert (tmp_path / "pkg" / "build" / "old").is_dir()


def test_wrong_confirmation_deletes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make(tmp_path)
    _terminal(monkeypatch, "yes")

    assert clean_build.main(["--root", str(tmp_path), "--all", "--execute"]) == 1
    assert (tmp_path / "pkg" / "build" / "old").is_dir()


def test_there_is_no_option_to_skip_the_confirmation(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        clean_build.main(["--root", str(tmp_path), "--all", "--execute", "--yes"])


def test_clean_keep_marker_protects_a_folder_and_everything_below(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make(tmp_path)
    (tmp_path / "pkg" / "build" / "new" / "clean.keep").write_text("")
    (tmp_path / "other" / "build" / "run").mkdir(parents=True)
    (tmp_path / "other" / "build" / "clean.keep").write_text("")
    _terminal(monkeypatch, "delete")

    assert clean_build.main(["--root", str(tmp_path), "--all", "--execute"]) == 0

    build = tmp_path / "pkg" / "build"
    assert not (build / "old").exists()
    assert (build / "new").is_dir()  # marker inside the run folder
    assert (tmp_path / "other" / "build" / "run").is_dir()  # marker in the build folder above


def test_hinv_is_not_scanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make(tmp_path)
    (tmp_path / "hinv" / "chip" / "build" / "run").mkdir(parents=True)
    _terminal(monkeypatch, "delete")

    assert clean_build.main(["--root", str(tmp_path), "--all", "--execute"]) == 0

    assert (tmp_path / "hinv" / "chip" / "build" / "run").is_dir()


def test_tracked_files_protect_a_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make(tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "pkg/build/old/file.txt"], check=True)
    _terminal(monkeypatch, "delete")

    assert clean_build.main(["--root", str(tmp_path), "--all", "--execute"]) == 0

    assert (tmp_path / "pkg" / "build" / "old").is_dir()
    assert not (tmp_path / "pkg" / "build" / "new").exists()
