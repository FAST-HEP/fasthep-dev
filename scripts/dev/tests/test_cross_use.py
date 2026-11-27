from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from scripts.dev import cross_use
from scripts.dev.tests.test_api_surface import make


def pair(tmp_path: Path) -> Path:
    snapshots = tmp_path / "build/review"
    same = "def _load(p):\n    return p\n"
    make(snapshots, "a", "pkg_a", {"io.py": same + "def run():\n    pass\n"})
    make(snapshots, "b", "pkg_b", {"io.py": same.replace("return p", "return 1") + "def _x():\n    pass\n"})
    (snapshots / "b/src/pkg_b/reg.yaml").write_text("impl: pkg_a.io:run\nbad: pkg_a.io:gone\nown: pkg_b.io:_x\n")
    (snapshots / "b/pyproject.toml").write_text('[project]\nrequires-python = ">=3.13"\ndependencies = ["fasthep-a>=0.2", "numpy"]\n')
    return snapshots


def test_duplicates_flag_same_name_in_two_repos(tmp_path):
    found = cross_use.duplicates(pair(tmp_path))
    assert [(d["name"], d["identical"], sorted(d["where"])) for d in found] == [("_load", False, ["a", "b"])]


def test_strings_report_crossing_and_missing_targets(tmp_path):
    found = {(s["target"], s["crosses"], s["missing"]) for s in cross_use.strings(pair(tmp_path))}
    assert found == {("pkg_a.io:run", True, False), ("pkg_a.io:gone", True, True)}


def test_floors_list_python_and_sibling_pins(tmp_path):
    assert cross_use.floors(pair(tmp_path))["b"] == {"requires-python": ">=3.13", "siblings": {"fasthep-a": "fasthep-a>=0.2"}}


def run_git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


def test_stale_rules(tmp_path):
    snapshots = tmp_path / "build/review"
    repo = snapshots / "a"
    repo.mkdir(parents=True)
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "t@t")
    run_git(repo, "config", "user.name", "t")
    (repo / "m.py").write_text("x = 1\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-qm", "one")
    reports = tmp_path / "reports"
    assert cross_use.stale(reports, snapshots, "a") == (True, ["no review yet"])
    run = reports / "a/2026-11-01"
    run.mkdir(parents=True)
    commit = run_git(repo, "rev-parse", "HEAD")
    (run / "findings.json").write_text(json.dumps({"commit": commit, "date": "2026-11-01"}))
    (run / "scope.txt").write_text("m.py 1\n")
    assert cross_use.stale(reports, snapshots, "a", date(2026, 11, 10)) == (False, [])
    assert cross_use.stale(reports, snapshots, "a", date(2026, 12, 20))[1] == ["49 days old (limit 30)"]
    (repo / "m.py").write_text("x = 2\n")
    run_git(repo, "commit", "-qam", "two")
    assert cross_use.stale(reports, snapshots, "a", date(2026, 11, 10)) == (True, ["1 reviewed files changed"])
