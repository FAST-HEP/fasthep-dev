from __future__ import annotations

from datetime import date

import pytest

from scripts.dev import roadmap


def _node(area: str = "flow", **kw):
    return {"title": kw.pop("title", "t"), "area": area, "kind": "work", "status": "open", **kw}


def _graph(**nodes):
    return {"version": 1, "areas": {"flow": "Flow", "cli": "CLI", "chip": "Chip"}, "nodes": nodes}


def test_valid_graph_has_no_errors() -> None:
    g = _graph(a=_node(), b=_node(depends_on=["a"]))

    assert roadmap.validate(g) == []


def test_unknown_dependency_and_unknown_area_are_errors() -> None:
    g = _graph(a=_node(depends_on=["missing"]), b=_node(area="nowhere"))

    errors = roadmap.validate(g)

    assert any("a" in e and "missing" in e for e in errors)
    assert any("b" in e and "nowhere" in e for e in errors)


def test_invalid_enum_values_are_errors() -> None:
    g = _graph(a=_node(status="soonish", size="HUGE"))

    errors = roadmap.validate(g)

    assert any("status" in e for e in errors) and any("size" in e for e in errors)


def test_a_cycle_is_an_error_and_names_the_nodes() -> None:
    g = _graph(a=_node(depends_on=["b"]), b=_node(soft_depends_on=["a"]))

    errors = roadmap.validate(g)

    assert any("cycle" in e and "a" in e and "b" in e for e in errors)


def test_a_node_cannot_depend_on_itself() -> None:
    assert any("itself" in e for e in roadmap.validate(_graph(a=_node(depends_on=["a"]))))


def test_a_done_node_with_an_open_hard_dependency_is_an_error() -> None:
    g = _graph(a=_node(), b=_node(status="done", depends_on=["a"]))

    assert any("done" in e and "b" in e for e in roadmap.validate(g))


def test_layers_follow_the_longest_chain_and_count_soft_dependencies() -> None:
    g = _graph(a=_node(), b=_node(depends_on=["a"]), c=_node(soft_depends_on=["b"]), d=_node(depends_on=["a"]))

    layers = roadmap.layers(g)

    assert layers == {"a": 0, "b": 1, "c": 2, "d": 1}


def test_ready_ignores_soft_dependencies_and_leaves_out_decisions_and_externals() -> None:
    g = _graph(
        a=_node(),
        b=_node(depends_on=["a"]),
        c=_node(soft_depends_on=["a"]),
        d=_node(kind="decision"),
        e=_node(area="chip", kind="external"),
        f=_node(status="deferred"),
    )

    assert roadmap.ready(g) == ["a", "c"]


def test_ready_treats_a_done_dependency_as_met() -> None:
    g = _graph(a=_node(status="done"), b=_node(depends_on=["a"]))

    assert roadmap.ready(g) == ["b"]


def test_critical_path_is_the_longest_chain() -> None:
    g = _graph(a=_node(), b=_node(depends_on=["a"]), c=_node(depends_on=["b"]), d=_node(depends_on=["a"]))

    assert roadmap.critical_path(g) == ["a", "b", "c"]


START = date(2026, 11, 4)


def _gantt(graph) -> str:
    text = roadmap.render_markdown(graph, start=START)
    return text.split("```mermaid")[1].split("```")[0]


def test_markdown_has_a_gantt_with_a_section_per_area_and_the_stage_list() -> None:
    g = _graph(
        a=_node(),
        b=_node(area="cli", depends_on=["a"]),
        c=_node(stages=["S0 first", "S1 second"]),
    )

    text = roadmap.render_markdown(g, start=START)

    assert "flowchart" not in text
    gantt = _gantt(g)
    assert gantt.lstrip().startswith("gantt")
    assert "dateFormat YYYY-MM-DD" in gantt
    assert "section Flow" in gantt and "section CLI" in gantt
    assert "S0 first" in text and "S1 second" in text


def test_schedule_starts_each_item_when_everything_it_waits_on_has_ended() -> None:
    g = _graph(
        a=_node(size="S"),
        b=_node(size="L", depends_on=["a"]),
        c=_node(size="M", soft_depends_on=["b"]),
        d=_node(kind="decision"),
        e=_node(depends_on=["d", "a"], size="S"),
    )

    plan = roadmap.schedule(g)

    assert plan["a"] == (0, 7)
    assert plan["b"] == (7, 28)
    assert plan["c"] == (35, 14)
    assert plan["d"] == (0, 0)  # a decision is a zero-length marker
    assert plan["e"] == (7, 7)


def test_gantt_uses_absolute_dates_not_after_references() -> None:
    g = _graph(a=_node(size="S"), b=_node(size="L", depends_on=["a"]), c=_node(size="M", soft_depends_on=["b"]))

    gantt = _gantt(g)

    assert "a, 2026-11-04, 7d" in gantt
    assert "b, 2026-11-11, 28d" in gantt
    assert "c, 2026-12-09, 14d" in gantt
    assert "after" not in gantt


def test_gantt_highlights_high_priority_work_and_its_prerequisites_and_marks_in_progress_as_active() -> None:
    g = _graph(
        a=_node(),
        b=_node(depends_on=["a"], priority="high"),
        z=_node(status="in_progress"),
        long1=_node(),
        long2=_node(depends_on=["long1"]),
        long3=_node(depends_on=["long2"]),
    )

    gantt = _gantt(g)

    assert "crit, a," in gantt and "crit, b," in gantt
    assert "active, z," in gantt
    assert "crit, long" not in gantt  # the longest chain is not what is highlighted


def test_gantt_shows_decisions_and_external_work_as_milestones_and_flags_blocked_work() -> None:
    g = _graph(
        d=_node(kind="decision", title="Pick one"),
        x=_node(area="chip", kind="external", title="Chip thing"),
        w=_node(status="blocked", depends_on=["d"], title="Needs the decision"),
    )

    gantt = _gantt(g)

    assert "milestone, d, 2026-11-04, 0d" in gantt
    assert "milestone, x, 2026-11-04, 0d" in gantt
    assert "Needs the decision (blocked) :" in gantt


def test_gantt_labels_cannot_break_the_syntax() -> None:
    g = _graph(a=_node(title="Foo: bar; baz #1 [x]"))

    gantt = _gantt(g)

    line = [line for line in gantt.split("\n") if " :a," in line or " :crit, a," in line][0]
    label = line.split(" :")[0]
    assert label.strip() == "Foo - bar, baz 1 (x)"
    assert ":" not in label and ";" not in label and "#" not in label and "[" not in label


def test_effort_days_can_be_overridden_and_xl_is_a_size() -> None:
    g = _graph(a=_node(size="XL"))
    g["effort_days"] = {"XL": 70}

    assert roadmap.validate(g) == []
    assert "a, 2026-11-04, 70d" in _gantt(g)


def test_markdown_lists_work_without_an_issue_and_the_ready_nodes() -> None:
    g = _graph(a=_node(), b=_node(issue=["https://x/1"]))

    text = roadmap.render_markdown(g)

    assert "Without an issue" in text
    assert text.index("Ready now") < text.index("Ordered layers")


def test_main_check_fails_on_a_bad_graph_and_prints_the_errors(tmp_path, capsys) -> None:
    path = tmp_path / "graph.yaml"
    path.write_text(
        "version: 1\nareas: {flow: Flow}\nnodes:\n  a: {title: t, area: flow, kind: work, status: open, depends_on: [zzz]}\n",
        encoding="utf-8",
    )

    code = roadmap.main(["--graph", str(path), "--check"])

    assert code == 1
    assert "zzz" in capsys.readouterr().out


def test_main_write_creates_the_file_only_when_asked(tmp_path) -> None:
    path = tmp_path / "graph.yaml"
    path.write_text(
        "version: 1\nareas: {flow: Flow}\nnodes:\n  a: {title: t, area: flow, kind: work, status: open}\n",
        encoding="utf-8",
    )
    out = tmp_path / "roadmap.md"

    assert roadmap.main(["--graph", str(path)]) == 0
    assert not out.exists()
    assert roadmap.main(["--graph", str(path), "--write", str(out)]) == 0
    assert "Ready now" in out.read_text(encoding="utf-8")


def test_a_bad_graph_is_never_written(tmp_path) -> None:
    path = tmp_path / "graph.yaml"
    path.write_text(
        "version: 1\nareas: {flow: Flow}\nnodes:\n  a: {title: t, area: flow, kind: work, status: open, depends_on: [a]}\n",
        encoding="utf-8",
    )
    out = tmp_path / "roadmap.md"

    with pytest.raises(SystemExit):
        roadmap.main(["--graph", str(path), "--write", str(out)])

    assert not out.exists()


def test_critical_path_follows_hard_dependencies_only() -> None:
    g = _graph(
        a=_node(),
        b=_node(soft_depends_on=["a"]),
        c=_node(soft_depends_on=["b"]),
        x=_node(),
        y=_node(depends_on=["x"]),
    )

    assert roadmap.critical_path(g) == ["x", "y"]
    assert roadmap.critical_path(g, hard_only=False) == ["a", "b", "c"]


def test_ready_lists_high_priority_first_then_the_earlier_layer() -> None:
    g = _graph(
        low=_node(priority="low"),
        late=_node(soft_depends_on=["low"]),
        urgent=_node(priority="high", soft_depends_on=["late"]),
        plain=_node(),
    )

    assert roadmap.ready(g) == ["urgent", "plain", "late", "low"]


def test_prerequisites_are_the_transitive_hard_dependencies_in_order() -> None:
    g = _graph(
        a=_node(),
        b=_node(depends_on=["a"]),
        c=_node(depends_on=["b"], priority="high"),
        s=_node(soft_depends_on=["c"]),
        d=_node(status="done"),
        e=_node(depends_on=["d", "c"]),
    )

    assert roadmap.prerequisites(g, "c") == ["a", "b"]
    assert roadmap.prerequisites(g, "e") == ["a", "b", "c"]  # the done one is not a prerequisite


def test_markdown_shows_what_unblocks_high_priority_work() -> None:
    g = _graph(a=_node(title="First step"), c=_node(depends_on=["a"], priority="high", title="Big thing"))

    text = roadmap.render_markdown(g)

    assert "Unblocking high-priority work" in text
    section = text.split("Unblocking high-priority work")[1].split("## ")[0]
    assert "Big thing" in section and "First step" in section


def test_a_prerequisite_of_high_priority_work_inherits_its_priority_in_ready() -> None:
    g = _graph(
        gate=_node(),
        big=_node(depends_on=["gate"], priority="high"),
        other=_node(),
        soft_only=_node(),
        follower=_node(soft_depends_on=["soft_only"], priority="high"),
    )

    assert roadmap.ready(g) == ["gate", "follower", "other", "soft_only"]
    assert roadmap.inherited_priority(g) == {"gate": "big"}  # soft dependencies do not inherit
    assert "high (unblocks `big`)" in roadmap.render_markdown(g)
