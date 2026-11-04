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
from pathlib import Path
from typing import Any

import yaml

KINDS = {"work", "epic", "decision", "milestone", "external", "tracker"}
STATUSES = {"open", "in_progress", "blocked", "deferred", "done"}
PRIORITIES = {"high", "normal", "low"}
SIZES = {"S", "M", "L"}
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


def _label(title: str, limit: int = 62) -> str:
    text = title if len(title) <= limit else title[: limit - 1] + "…"
    return text.replace('"', "#quot;").replace("[", "(").replace("]", ")")


def _shape(kind: str, label: str) -> str:
    return {
        "decision": '{{"%s"}}',
        "epic": '[["%s"]]',
        "milestone": '(["%s"])',
        "external": '("%s")',
    }.get(kind, '["%s"]') % label


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
        "Generated from `graph.yaml` by `scripts/dev/roadmap.py`: edit the data, never this file.",
        f"{len(nodes)} nodes. Solid arrows are hard dependencies, dashed arrows are ordering (soft). "
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

    out += ["## Graph", "", "```mermaid", "flowchart TD"]
    for area, area_title in areas.items():
        members = [k for k, n in nodes.items() if n["area"] == area]
        if not members:
            continue
        out.append(f'  subgraph {area}["{_label(area_title)}"]')
        for key in members:
            n = nodes[key]
            out.append(f"    {_mid(key)}{_shape(n['kind'], _label(n['title']))}")
        out.append("  end")
    for key, n in nodes.items():
        for dep in n.get("depends_on") or []:
            if dep in nodes:
                out.append(f"  {_mid(dep)} --> {_mid(key)}")
        for dep in n.get("soft_depends_on") or []:
            if dep in nodes:
                out.append(f"  {_mid(dep)} -.-> {_mid(key)}")
    out.append("  classDef external stroke-dasharray: 4 3,fill:#f2f2f2,color:#555")
    out.append("  classDef decision fill:#fff3cd,stroke:#b8860b")
    out.append("  classDef high stroke-width:3px")
    for cls, selector in (("external", lambda n: n["kind"] == "external"),
                          ("decision", lambda n: n["kind"] == "decision"),
                          ("high", lambda n: n.get("priority") == "high")):
        picked = [_mid(k) for k, n in nodes.items() if selector(n)]
        if picked:
            out.append(f"  class {','.join(picked)} {cls}")
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
    text = render_markdown(graph)
    if args.write:
        args.write.write_text(text, encoding="utf-8")
        print(f"wrote {args.write}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
