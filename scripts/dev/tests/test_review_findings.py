from __future__ import annotations

import json
from pathlib import Path

from scripts.dev import review_findings as rf


def finding(symbol: str, lines: int = -10, **extra) -> dict:
    return {
        "category": "duplication", "file": "src/a.py", "symbol": symbol, "line": 5,
        "summary": "s", "proposal": "p", "est_lines": lines, "risk": "none", **extra,
    }


def run_dir(root: Path, name: str, findings: list[dict], agents: list[dict] | None = None) -> Path:
    path = root / name
    path.mkdir()
    (path / "findings.json").write_text(json.dumps({
        "schema_version": 1, "repo": "flow", "commit": "abc", "mode": "full", "date": "2026-11-27",
        "findings": findings}))
    cost = {"schema_version": 1, "budget_tokens": 100, "agents": agents or [
        {"role": "r", "tokens": 60, "tool_uses": 3, "duration_ms": 1, "findings": 2, "lines_in_scope": 1000}]}
    (path / "cost.json").write_text(json.dumps(cost))
    return path


def test_fingerprint_ignores_line_and_text():
    assert rf.fingerprint(finding("f")) == rf.fingerprint({**finding("f"), "line": 99, "summary": "other"})
    assert rf.fingerprint(finding("f")) != rf.fingerprint(finding("g"))
    assert rf.fingerprint(finding("f")) != rf.fingerprint(finding("f", key="second"))


def test_stamp_then_check_ok(tmp_path, capsys):
    path = run_dir(tmp_path, "a", [finding("f"), finding("g")])
    assert rf.main(["check", str(path)]) == 1  # ids missing
    assert rf.main(["stamp", str(path / "findings.json")]) == 0
    capsys.readouterr()
    assert rf.main(["check", str(path)]) == 0
    assert "tokens per finding 30" in capsys.readouterr().out


def test_check_flags_duplicate_budget_and_bad_category(tmp_path, capsys):
    bad = finding("f", category="nonsense")
    path = run_dir(tmp_path, "a", [finding("f"), finding("f"), bad], agents=[
        {"role": "r", "tokens": 500, "tool_uses": 1, "duration_ms": 1, "findings": 1, "lines_in_scope": 10}])
    rf.main(["stamp", str(path / "findings.json")])
    capsys.readouterr()
    assert rf.main(["check", str(path)]) == 1
    out = capsys.readouterr().out
    assert "duplicate id" in out
    assert "category must be one of" in out
    assert "over budget" in out


def test_diff_new_resolved_persisting_changed(tmp_path, capsys):
    old = run_dir(tmp_path, "old", [finding("keep"), finding("gone"), finding("size", -10)])
    new = run_dir(tmp_path, "new", [finding("keep"), finding("fresh"), finding("size", -40)])
    for run in (old, new):
        rf.main(["stamp", str(run / "findings.json")])
    capsys.readouterr()
    assert rf.main(["diff", str(old), str(new), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {k: [f["symbol"] for f in v] for k, v in out.items()} == {
        "new": ["fresh"], "resolved": ["gone"], "persisting": ["keep"], "changed": ["size"]}
