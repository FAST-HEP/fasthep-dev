#!/usr/bin/env python3
"""Validate the FAST-HEP roadmap graph and generate the ordered roadmap from it.

The data lives in ``tasks/<date>-roadmap/graph.yaml`` (the source of truth); this tool never edits it.
Read-only by default: it prints the generated markdown. ``--check`` only validates (cycles, unknown ids,
bad values, a done item with an open dependency) and checks coverage (a task folder or a mirrored open issue
that no node accounts for), exiting non-zero on any problem; it also warns (never fails) about new task folders that
break the naming convention. ``--write [PATH]`` writes the generated markdown
(default ``ROADMAP.md`` next to the graph), and refuses to if there is any problem. FAST-HEP only: chip (``hinv/``) appears only
as external nodes in the data and is never read.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

KINDS = {"work", "epic", "decision", "milestone", "external", "tracker"}
STATUSES = {"open", "in_progress", "blocked", "deferred", "done"}
PRIORITIES = {"high", "normal", "low"}
SIZES = {"S", "M", "L", "XL"}
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
DEFAULT_GRAPH = Path("tasks/roadmap.yaml")
TASK_FOLDER = re.compile(r"^\d{4}-\d{2}-\d{2}-")
NEW_TASK_NAME = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<target>[a-z0-9]+(?:\+[a-z0-9]+)*)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
ISSUE_FILE = re.compile(r"^github-(?P<repo>.+?)-(?P<number>\d+)-")


def load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), dict):
        raise SystemExit(f"{path}: expected a mapping with a 'nodes' mapping")
    return data


def _deps(node: dict[str, Any]) -> list[str]:
    return list(node.get("depends_on") or []) + list(node.get("soft_depends_on") or [])


def validate(graph: dict[str, Any]) -> list[str]:
    nodes: dict[str, dict[str, Any]] = graph["nodes"]
    areas = graph.get("areas") or {}
    errors: list[str] = []
    for key, node in nodes.items():
        for field in ("title", "area", "kind", "status"):
            if field not in node:
                errors.append(f"{key}: missing '{field}'")
        if node.get("area") not in areas:
            errors.append(f"{key}: unknown area '{node.get('area')}'")
        if node.get("kind") not in KINDS:
            errors.append(f"{key}: invalid kind '{node.get('kind')}'")
        if node.get("status") not in STATUSES:
            errors.append(f"{key}: invalid status '{node.get('status')}'")
        if node.get("priority", "normal") not in PRIORITIES:
            errors.append(f"{key}: invalid priority '{node.get('priority')}'")
        if node.get("size", "M") not in SIZES:
            errors.append(f"{key}: invalid size '{node.get('size')}'")
        for dep in _deps(node):
            if dep == key:
                errors.append(f"{key}: depends on itself")
            elif dep not in nodes:
                errors.append(f"{key}: depends on unknown id '{dep}'")
        if node.get("status") == "done":
            for dep in node.get("depends_on") or []:
                if dep in nodes and nodes[dep].get("status") != "done":
                    errors.append(f"{key}: is done but depends on '{dep}', which is {nodes[dep].get('status')}")
    for kind, items in (graph.get("retired") or {}).items():
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            errors.append(f"retired.{kind}: must be a list of plain strings (a ': ' inside [...] makes a mapping)")
    cycle = _find_cycle(nodes)
    if cycle:
        errors.append("cycle: " + " -> ".join(cycle))
    return errors


def _find_cycle(nodes: dict[str, dict[str, Any]]) -> list[str]:
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(nodes, WHITE)
    stack: list[str] = []

    def visit(key: str) -> list[str]:
        colour[key] = GREY
        stack.append(key)
        for dep in _deps(nodes[key]):
            if dep not in nodes or dep == key:
                continue
            if colour[dep] == GREY:
                return stack[stack.index(dep):] + [dep]
            if colour[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        colour[key] = BLACK
        return []

    for key in nodes:
        if colour[key] == WHITE:
            found = visit(key)
            if found:
                return found
    return []


def layers(graph: dict[str, Any]) -> dict[str, int]:
    """Longest-chain layer of every node over hard and soft dependencies (done dependencies ignored)."""
    nodes = graph["nodes"]
    memo: dict[str, int] = {}

    def layer(key: str) -> int:
        if key not in memo:
            deps = [d for d in _deps(nodes[key]) if d in nodes and nodes[d].get("status") != "done"]
            memo[key] = 1 + max(layer(d) for d in deps) if deps else 0
        return memo[key]

    return {key: layer(key) for key in nodes}


def _hard_unmet(graph: dict[str, Any], key: str) -> list[str]:
    nodes = graph["nodes"]
    return [d for d in nodes[key].get("depends_on") or [] if d in nodes and nodes[d].get("status") != "done"]


def _order_key(graph: dict[str, Any], key: str) -> tuple[int, str]:
    return (PRIORITY_ORDER.get(graph["nodes"][key].get("priority", "normal"), 1), key)


def inherited_priority(graph: dict[str, Any]) -> dict[str, str]:
    """Prerequisites of high-priority work -> the high-priority node they unblock (hard dependencies only)."""
    out: dict[str, str] = {}
    for key, node in graph["nodes"].items():
        if node.get("priority") == "high" and node["status"] != "done":
            for pre in prerequisites(graph, key):
                out.setdefault(pre, key)
    return out


def ready(graph: dict[str, Any]) -> list[str]:
    """Open or in-progress FAST-HEP work with no unmet hard dependency (soft ones only order).

    Highest priority first, then the earlier layer (it unblocks more).
    """
    out = [
        key
        for key, node in graph["nodes"].items()
        if node["status"] in ("open", "in_progress")
        and node["kind"] in ("work", "epic")
        and not _hard_unmet(graph, key)
    ]
    layer = layers(graph)
    boosted = inherited_priority(graph)
    return sorted(out, key=lambda k: (0 if k in boosted else _order_key(graph, k)[0], layer[k], k))


def _chain_deps(node: dict[str, Any], hard_only: bool) -> list[str]:
    return list(node.get("depends_on") or []) if hard_only else _deps(node)


def critical_path(graph: dict[str, Any], hard_only: bool = True) -> list[str]:
    """Longest dependency chain. Hard dependencies only by default: a chain of soft links is only an ordering."""
    nodes = graph["nodes"]
    memo: dict[str, int] = {}

    def depth(key: str) -> int:
        if key not in memo:
            deps = [d for d in _chain_deps(nodes[key], hard_only) if d in nodes and nodes[d].get("status") != "done"]
            memo[key] = 1 + max(depth(d) for d in deps) if deps else 0
        return memo[key]

    if not nodes:
        return []
    end = max(nodes, key=lambda k: (depth(k), k))
    path = [end]
    while True:
        deps = [d for d in _chain_deps(nodes[path[-1]], hard_only) if d in nodes and nodes[d].get("status") != "done"]
        if not deps:
            return list(reversed(path))
        path.append(max(deps, key=lambda d: (depth(d), d)))


def prerequisites(graph: dict[str, Any], key: str) -> list[str]:
    """Transitive hard dependencies of a node that are not done, earliest layer first."""
    nodes = graph["nodes"]
    seen: set[str] = set()

    def walk(k: str) -> None:
        for d in nodes[k].get("depends_on") or []:
            if d in nodes and d not in seen and nodes[d].get("status") != "done":
                seen.add(d)
                walk(d)

    walk(key)
    layer = layers(graph)
    return sorted(seen, key=lambda k: (layer[k], k))


def _issue_cell(node: dict[str, Any]) -> str:
    links = []
    for url in node.get("issue") or []:
        repo, num = url.rstrip("/").split("/")[-3], url.rstrip("/").split("/")[-1]
        links.append(f"[{repo.replace('fasthep-', '')}#{num}]({url})")
    return ", ".join(links) if links else "none"


def render_markdown(graph: dict[str, Any]) -> str:
    nodes: dict[str, dict[str, Any]] = graph["nodes"]
    areas: dict[str, str] = graph.get("areas") or {}
    layer = layers(graph)
    out = [
        "# FAST-HEP roadmap",
        "",
        "Generated from `roadmap.yaml` by `scripts/dev/roadmap.py` (`pixi run roadmap-write`): edit the data, never this file.",
        f"{len(nodes)} nodes. Hard dependencies block; soft ones only order. "
        "Chip nodes are external: shown for what FAST-HEP items wait on or feed.",
        "",
        "## Ready now",
        "",
        "Open or in-progress FAST-HEP work with no unmet hard dependency, earliest layer and priority first.",
        "",
        "| Item | Area | Size | Priority | Issue | Better after (soft) |",
        "|---|---|---|---|---|---|",
    ]
    boosted = inherited_priority(graph)
    for key in ready(graph):
        n = nodes[key]
        priority = f"high (unblocks `{boosted[key]}`)" if key in boosted else n.get("priority", "normal")
        soft = ", ".join(f"`{d}`" for d in n.get("soft_depends_on") or [] if nodes.get(d, {}).get("status") != "done")
        out.append(
            f"| `{key}`: {n['title']} | {n['area']} | {n.get('size', '-')} | {priority} "
            f"| {_issue_cell(n)} | {soft} |"
        )

    high = [k for k, n in nodes.items() if n.get("priority") == "high" and n["status"] != "done" and prerequisites(graph, k)]
    if high:
        out += ["", "## Unblocking high-priority work", "",
                "High-priority items that are blocked, with everything that must happen first (hard dependencies, earliest first).", ""]
        for k in high:
            out.append(f"- `{k}`: {nodes[k]['title']}")
            out += [f"  {i}. `{p}`: {nodes[p]['title']} ({nodes[p]['status']})"
                    for i, p in enumerate(prerequisites(graph, k), 1)]

    decisions = [k for k, n in nodes.items() if n["kind"] == "decision" and n["status"] != "done"]
    if decisions:
        out += ["", "## Decisions open", ""]
        out += [f"- `{k}`: {nodes[k]['title']}" for k in decisions]

    out += ["", "## Ordered layers", "", "Layer 0 has no dependencies; each later layer waits on an earlier one.", "",
            "| Layer | Item | Area | Size | Status | After (hard) | Also after (soft) |", "|---|---|---|---|---|---|---|"]
    for key in sorted(nodes, key=lambda k: (layer[k], *_order_key(graph, k))):
        n = nodes[key]
        hard = ", ".join(f"`{d}`" for d in n.get("depends_on") or []) or ""
        soft = ", ".join(f"`{d}`" for d in n.get("soft_depends_on") or []) or ""
        out.append(f"| {layer[key]} | `{key}`: {n['title']} | {n['area']} | {n.get('size', '-')} | {n['status']} | {hard} | {soft} |")

    path = critical_path(graph)
    out += ["", "## Longest chain of hard dependencies", "", " → ".join(f"`{k}`" for k in path), ""]

    staged = [(k, n) for k, n in nodes.items() if n.get("stages")]
    for key, n in staged:
        out += [f"## Stages of `{key}`", "", f"{n['title']}. Collapsed to one node in the graph above.", ""]
        out += [f"- {s}" for s in n["stages"]]
        out.append("")

    no_issue = [k for k, n in nodes.items() if n["kind"] in ("work", "epic") and not n.get("issue") and n["status"] != "done"]
    out += ["## Without an issue", "", "Seeds and other work with no issue yet. Each goes through the grilling skill first; the issue is then written from the grilled design, in its owning repository and on roadmap project 3.", ""]
    out += [f"- `{k}` ({nodes[k]['area']})" for k in no_issue]
    retired = graph.get("retired")
    if retired:
        out += ["", "## Retired from the roadmap", ""]
        out += [f"- {kind}: {', '.join(items)}" for kind, items in retired.items()]
    out.append("")
    return "\n".join(out)


def coverage(graph: dict[str, Any], tasks_dir: Path) -> list[str]:
    """Task folders and mirrored open issues that no node accounts for.

    A task folder counts when a node lists it (or a path inside it) under ``sources``, or the graph lists it under
    ``not_in_graph``. A mirrored issue (``issues/github-<repo>-<n>-*.md``) counts when a node has its URL.
    """
    nodes: dict[str, dict[str, Any]] = graph["nodes"]
    sourced = {str(src).split("/")[0] for n in nodes.values() for src in n.get("sources") or []}
    sourced |= set(graph.get("not_in_graph") or [])
    issues = set()
    for n in nodes.values():
        for url in n.get("issue") or []:
            parts = url.rstrip("/").split("/")
            issues.add((parts[-3], parts[-1]))
    errors: list[str] = []
    for folder in sorted(p.name for p in tasks_dir.iterdir() if p.is_dir() and TASK_FOLDER.match(p.name)):
        if folder not in sourced:
            errors.append(f"task folder {folder} has no node: add it to the sources of a node, or list it under not_in_graph")
    mirror = tasks_dir / "issues"
    if mirror.is_dir():
        for path in sorted(mirror.glob("github-*.md")):
            m = ISSUE_FILE.match(path.name)
            if m and (m["repo"], m["number"]) not in issues:
                errors.append(f"open issue {m['repo']}#{m['number']} has no node: add it (issue:) to a node")
    return errors


def naming_warnings(graph: dict[str, Any], tasks_dir: Path) -> list[str]:
    """One warning per task folder dated on or after ``task_naming.from`` that breaks the naming convention.

    ``YYYY-MM-DD-<target>-<slug>``: the target is one to ``max_named`` of the listed codes joined with ``+`` in
    alphabetical order, or ``multi`` alone for more; the slug is two to five lowercase words. Older folders keep
    their names. Warnings only: nothing here fails a check.
    """
    rule = graph.get("task_naming")
    if not rule:
        return []
    cutoff = str(rule["from"])
    targets = set(rule.get("targets") or [])
    limit = int(rule.get("max_named", 3))
    warnings: list[str] = []
    for folder in sorted(p.name for p in tasks_dir.iterdir() if p.is_dir() and TASK_FOLDER.match(p.name)):
        if folder[:10] < cutoff:
            continue
        m = NEW_TASK_NAME.match(folder)
        if not m:
            warnings.append(f"task folder {folder} does not match YYYY-MM-DD-<target>-<slug> "
                            "(lowercase letters, digits and hyphens; several targets joined with '+')")
            continue
        names = m["target"].split("+")
        reasons: list[str] = []
        if "multi" in names:
            if len(names) > 1:
                reasons.append("'multi' stands alone")
        else:
            unknown = [n for n in names if n not in targets]
            if unknown:
                reasons.append(f"unknown target {', '.join(unknown)} (valid: {', '.join(sorted(targets))}, multi)")
            if len(set(names)) != len(names):
                reasons.append("a target is repeated")
            elif names != sorted(names):
                reasons.append("targets must be in alphabetical order")
            if len(names) > limit:
                reasons.append(f"names {len(names)} repositories: more than {limit} should be 'multi'")
        words = len(m["slug"].split("-"))
        if not 2 <= words <= 5:
            reasons.append(f"the slug has {words} word(s), expected 2 to 5")
        if reasons:
            warnings.append(f"task folder {folder}: " + "; ".join(reasons))
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--tasks-dir", type=Path, default=None,
                        help="folder checked for tasks and mirrored issues without a node (default: the graph's folder)")
    parser.add_argument("--check", action="store_true",
                        help="only validate and check coverage; print problems, exit 1 if any")
    parser.add_argument("--write", nargs="?", const=True, default=None, type=Path, metavar="PATH",
                        help="write the generated markdown (default: ROADMAP.md next to the graph)")
    args = parser.parse_args(argv)

    graph = load(args.graph)
    tasks_dir = args.tasks_dir or args.graph.parent
    if tasks_dir.is_dir():
        for warning in naming_warnings(graph, tasks_dir):
            print(f"warning: {warning}", file=sys.stdout if args.check else sys.stderr)
    errors = validate(graph)
    if not errors and tasks_dir.is_dir():
        errors = coverage(graph, tasks_dir)
    if errors:
        for error in errors:
            print(f"error: {error}")
        if args.write:
            raise SystemExit(f"not writing the roadmap: {len(errors)} problem(s)")
        return 1
    if args.check:
        print(f"{args.graph}: {len(graph['nodes'])} nodes, no problems")
        return 0
    text = render_markdown(graph)
    if args.write:
        out = args.graph.parent / "ROADMAP.md" if args.write is True else args.write
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
