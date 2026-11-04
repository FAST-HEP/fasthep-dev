#!/usr/bin/env python3
"""Validate the FAST-HEP roadmap graph and generate the ordered roadmap from it.

The data lives in ``tasks/<date>-roadmap/graph.yaml`` (the source of truth); this tool never edits it.
Read-only by default: it prints the generated markdown. ``--check`` only validates (cycles, unknown ids,
bad values, a done item with an open dependency) and exits non-zero on any problem. ``--write PATH`` writes
the generated markdown, and refuses to if the graph is invalid. FAST-HEP only: chip (``hinv/``) appears only
as external nodes in the data and is never read.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

KINDS = {"work", "epic", "decision", "milestone", "external", "tracker"}
STATUSES = {"open", "in_progress", "blocked", "deferred", "done"}
PRIORITIES = {"high", "normal", "low"}
SIZES = {"S", "M", "L", "XL"}
EFFORT_DAYS = {"S": 7, "M": 14, "L": 28, "XL": 56}
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
DEFAULT_GRAPH = Path("tasks/2026-11-04-roadmap/graph.yaml")


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


def _mid(key: str) -> str:
    return key.replace("-", "_")


def _gantt_label(title: str, limit: int = 56) -> str:
    """Gantt task titles end at the first colon; ';', '#' and brackets also break the parser."""
    text = title.replace(":", " -").replace(";", ",").replace("#", "").replace("[", "(").replace("]", ")")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _issue_cell(node: dict[str, Any]) -> str:
    links = []
    for url in node.get("issue") or []:
        repo, num = url.rstrip("/").split("/")[-3], url.rstrip("/").split("/")[-1]
        links.append(f"[{repo.replace('fasthep-', '')}#{num}]({url})")
    return ", ".join(links) if links else "none"


def schedule(graph: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """(start offset, duration) in days: an item starts when everything it waits on (hard or soft) has ended."""
    nodes: dict[str, dict[str, Any]] = graph["nodes"]
    effort = {**EFFORT_DAYS, **(graph.get("effort_days") or {})}
    memo: dict[str, tuple[int, int]] = {}

    def plan(key: str) -> tuple[int, int]:
        if key not in memo:
            n = nodes[key]
            deps = [d for d in _deps(n) if d in nodes and nodes[d].get("status") != "done"]
            begin = max((plan(d)[0] + plan(d)[1] for d in deps), default=0)
            length = 0 if n["kind"] in ("decision", "external", "tracker", "milestone") else effort[n.get("size", "M")]
            memo[key] = (begin, length)
        return memo[key]

    return {key: plan(key) for key in nodes}


def render_gantt(graph: dict[str, Any], start: date) -> list[str]:
    """Mermaid gantt: bars last by size and start after everything they wait on (hard or soft).

    Start dates are computed here (see `schedule`) so the chart does not depend on how Mermaid resolves
    ``after`` references across sections.

    Not a forecast: durations are placeholders from the size, capacity is unlimited, and decisions and
    external (chip) work are zero-length milestones that only fix the order. High-priority work and its
    prerequisites are highlighted.
    """
    nodes: dict[str, dict[str, Any]] = graph["nodes"]
    areas: dict[str, str] = graph.get("areas") or {}
    layer = layers(graph)
    plan = schedule(graph)
    highlighted = set(inherited_priority(graph)) | {k for k, n in nodes.items() if n.get("priority") == "high"}
    out = [
        "gantt",
        "  title Roadmap order (sizes as placeholder durations, unlimited capacity, not a forecast)",
        "  dateFormat YYYY-MM-DD",
        "  axisFormat %d %b",
    ]
    for area, area_title in areas.items():
        members = sorted((k for k, n in nodes.items() if n["area"] == area), key=lambda k: (layer[k], k))
        if not members:
            continue
        out.append(f"  section {_gantt_label(area_title)}")
        for key in members:
            n = nodes[key]
            label = _gantt_label(n["title"])
            if n["status"] in ("blocked", "deferred"):
                label += f" ({n['status']})"
            offset, length = plan[key]
            begin = (start + timedelta(days=offset)).isoformat()
            if n["kind"] in ("decision", "external", "tracker", "milestone"):
                tags = "milestone"
            else:
                tags = "crit" if key in highlighted else ("active" if n["status"] == "in_progress" else "")
            prefix = f"{tags}, " if tags else ""
            out.append(f"  {label} :{prefix}{_mid(key)}, {begin}, {length}d")
    return out


def render_markdown(graph: dict[str, Any], start: date | None = None) -> str:
    nodes: dict[str, dict[str, Any]] = graph["nodes"]
    areas: dict[str, str] = graph.get("areas") or {}
    layer = layers(graph)
    out = [
        "# FAST-HEP roadmap",
        "",
        "Generated from `graph.yaml` by `scripts/dev/roadmap.py`: edit the data, never this file.",
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

    out += ["## Order over time", "",
            "Bars start after everything an item waits on (hard or soft) and last by size (S 1 week, M 2, L 4, XL 8 "
            "unless `effort_days` says otherwise). This is an order, not a forecast: capacity is unlimited, decisions "
            "and chip work are zero-length markers, high-priority work and what it needs first is highlighted.", "",
            "```mermaid"]
    out += render_gantt(graph, start or date.today())
    out += ["```", ""]

    staged = [(k, n) for k, n in nodes.items() if n.get("stages")]
    for key, n in staged:
        out += [f"## Stages of `{key}`", "", f"{n['title']}. Collapsed to one node in the graph above.", ""]
        out += [f"- {s}" for s in n["stages"]]
        out.append("")

    no_issue = [k for k, n in nodes.items() if n["kind"] in ("work", "epic") and not n.get("issue") and n["status"] != "done"]
    out += ["## Without an issue", "", "Real work that should get an issue in its owning repository and a place on roadmap project 3.", ""]
    out += [f"- `{k}` ({nodes[k]['area']})" for k in no_issue]
    retired = graph.get("retired")
    if retired:
        out += ["", "## Retired from the roadmap", ""]
        out += [f"- {kind}: {', '.join(items)}" for kind, items in retired.items()]
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--check", action="store_true", help="only validate; print problems, exit 1 if any")
    parser.add_argument("--write", type=Path, metavar="PATH", help="write the generated markdown to PATH")
    parser.add_argument("--start", type=date.fromisoformat, default=None, metavar="YYYY-MM-DD",
                        help="first day of the chart (default: today)")
    args = parser.parse_args(argv)

    graph = load(args.graph)
    errors = validate(graph)
    if errors:
        for error in errors:
            print(f"error: {error}")
        if args.write:
            raise SystemExit(f"not writing {args.write}: the graph has {len(errors)} problem(s)")
        return 1
    if args.check:
        print(f"{args.graph}: {len(graph['nodes'])} nodes, no problems")
        return 0
    text = render_markdown(graph, start=args.start)
    if args.write:
        args.write.write_text(text, encoding="utf-8")
        print(f"wrote {args.write}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
