#!/usr/bin/env python3
"""Stamp, check and diff the findings and cost files of a maintainability review run.

A run directory holds ``findings.json`` and ``cost.json`` (format: docs/review-format.md). A finding's
``id`` is a fingerprint of category, file, symbol and key, never of the line, so a finding keeps its id
while code moves around it. Read-only except ``stamp``, which writes ids into ``findings.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

CATEGORIES = {"duplication", "dead", "structure", "hypothesis", "cross-use"}
RISKS = {"none", "in-repo", "cross-package"}
FINDING_KEYS = {"category", "file", "summary", "proposal", "est_lines", "risk"}
AGENT_KEYS = {"role", "tokens", "tool_uses", "duration_ms", "findings", "lines_in_scope"}


def fingerprint(finding: dict) -> str:
    text = "|".join(str(finding.get(k, "")) for k in ("category", "file", "symbol", "key"))
    return hashlib.sha1(text.encode()).hexdigest()[:12]  # noqa: S324 - identity, not security


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_findings(data: dict) -> list[str]:
    errors = []
    seen = set()
    for number, finding in enumerate(data.get("findings", [])):
        label = f"findings[{number}]"
        if missing := FINDING_KEYS - finding.keys():
            errors.append(f"{label}: missing {sorted(missing)}")
        if finding.get("category") not in CATEGORIES:
            errors.append(f"{label}: category must be one of {sorted(CATEGORIES)}")
        if finding.get("risk") not in RISKS:
            errors.append(f"{label}: risk must be one of {sorted(RISKS)}")
        if finding.get("id") != fingerprint(finding):
            errors.append(f"{label}: id is not the fingerprint (run stamp)")
        if finding.get("id") in seen:
            errors.append(f"{label}: duplicate id; give one a distinct key")
        seen.add(finding.get("id"))
    for field in ("repo", "commit", "mode", "date"):
        if field not in data:
            errors.append(f"missing {field}")
    return errors


def check_cost(data: dict) -> tuple[list[str], list[str]]:
    errors, lines = [], []
    agents = data.get("agents", [])
    for number, agent in enumerate(agents):
        if missing := AGENT_KEYS - agent.keys():
            errors.append(f"agents[{number}]: missing {sorted(missing)}")
    tokens = sum(a.get("tokens", 0) for a in agents)
    found = sum(a.get("findings", 0) for a in agents)
    scope = sum(a.get("lines_in_scope", 0) for a in agents)
    lines.append(f"agents {len(agents)}, tokens {tokens:,}, findings {found}, lines in scope {scope:,}")
    if found:
        lines.append(f"tokens per finding {tokens // found:,}")
    if scope:
        lines.append(f"tokens per 1000 lines {tokens * 1000 // scope:,}")
    if (budget := data.get("budget_tokens")) and tokens > budget:
        errors.append(f"over budget: {tokens:,} > {budget:,} tokens")
    if data.get("main_session_tokens") is None:
        lines.append("main session tokens not recorded (not exposed by the harness)")
    return errors, lines


def diff(old: dict, new: dict) -> dict[str, list[dict]]:
    before = {f["id"]: f for f in old["findings"]}
    after = {f["id"]: f for f in new["findings"]}
    return {
        "new": [after[i] for i in after.keys() - before.keys()],
        "resolved": [before[i] for i in before.keys() - after.keys()],
        "persisting": [after[i] for i in after.keys() & before.keys() if after[i]["est_lines"] == before[i]["est_lines"]],
        "changed": [after[i] for i in after.keys() & before.keys() if after[i]["est_lines"] != before[i]["est_lines"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("stamp", help="write fingerprint ids into FINDINGS").add_argument("findings", type=Path)
    check = sub.add_parser("check", help="validate a run directory (findings.json, cost.json)")
    check.add_argument("run", type=Path)
    compare = sub.add_parser("diff", help="new, resolved, persisting and changed findings between two run directories")
    compare.add_argument("old", type=Path)
    compare.add_argument("new", type=Path)
    compare.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "stamp":
        data = load(args.findings)
        for finding in data["findings"]:
            finding["id"] = fingerprint(finding)
        args.findings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"stamped {len(data['findings'])} findings")
        return 0
    if args.command == "check":
        errors = check_findings(load(args.run / "findings.json"))
        cost_errors, summary = check_cost(load(args.run / "cost.json"))
        print("\n".join(summary))
        errors += cost_errors
        print("\n".join(errors) if errors else "ok")
        return int(bool(errors))
    result = diff(load(args.old / "findings.json"), load(args.new / "findings.json"))
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    for name, items in result.items():
        print(f"{name}: {len(items)} ({sum(f['est_lines'] for f in items):+d} est. lines)")
        for finding in sorted(items, key=lambda f: f["est_lines"]):
            print(f"  {finding['id']} {finding['category']:<11} {finding['file']} {finding.get('symbol', '')} ({finding['est_lines']:+d})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
