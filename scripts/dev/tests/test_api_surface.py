from __future__ import annotations

from pathlib import Path

from scripts.dev import api_surface


def make(root: Path, repo: str, module: str, files: dict[str, str], tests: str = "") -> None:
    package = root / repo / "src" / module
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    for name, text in files.items():
        (package / name).write_text(text)
    (root / repo / "tests").mkdir()
    (root / repo / "tests" / "test_x.py").write_text(tests)


def workspace(tmp_path: Path) -> Path:
    snapshots = tmp_path / "build/review"
    make(
        snapshots, "flow", "hepflow",
        {"api.py": "def run():\n    pass\n\ndef unused():\n    pass\n\ndef _hidden():\n    pass\n"},
    )
    make(
        snapshots, "carp", "carpenter",
        {"ops.py": "from hepflow.api import run, _hidden\nimport hepflow.api as api\n\nVALUE = api.run\n"},
        tests="from hepflow import api\n\napi.unused\n",
    )
    return tmp_path


def test_unused_public_and_private_imports(tmp_path, capsys):
    root = workspace(tmp_path)
    assert api_surface.main(["--root", str(root), "--repo", "flow"]) == 0
    out = capsys.readouterr().out
    assert "0 of 2 public symbols have no sibling user" in out  # `unused` is used by a sibling test
    assert "carp (src) -> hepflow.api._hidden" in out


def test_unused_symbol_is_listed_and_private_fails(tmp_path, capsys):
    root = workspace(tmp_path)
    (root / "build/review/carp/tests/test_x.py").write_text("")
    assert api_surface.main(["--root", str(root), "--repo", "flow", "--fail-on-private"]) == 1
    assert "  hepflow.api: unused" in capsys.readouterr().out


def test_missing_snapshots(tmp_path, capsys):
    assert api_surface.main(["--root", str(tmp_path)]) == 2
    assert "no snapshots" in capsys.readouterr().err
