from __future__ import annotations

from scripts.dev import tasks_sync

ITEM = {
    "source": "github", "repository": "FAST-HEP/fasthep-flow", "number": 86, "kind": "issue",
    "title": "Resolve path-typed params, at compile time!", "body": "Body text\n", "state": "OPEN",
    "url": "https://github.com/FAST-HEP/fasthep-flow/issues/86", "updated": "2026-10-21T11:31:48Z",
    "status": "Backlog", "labels": ["a", "b"],
}


def test_filename_is_stable_and_safe() -> None:
    assert tasks_sync.filename(ITEM) == "github-fasthep-flow-86-resolve-path-typed-params-at-compile-time.md"


def test_render_marks_generated_files_and_keeps_the_body() -> None:
    text = tasks_sync.render(ITEM)

    assert tasks_sync.MARKER in text
    assert "project-status: Backlog" in text and "labels: [a, b]" in text
    assert text.endswith("# Resolve path-typed params, at compile time!\n\nBody text\n")


def test_load_tokens_prefers_environment_and_never_needs_a_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")
    env_file = tmp_path / "t.env"
    env_file.write_text("GITHUB_TOKEN=from-file\nexport GITLAB_TOKEN='glpat-x'\nOTHER=1\n")

    tokens = tasks_sync.load_tokens(env_file)

    assert tokens == {"GITHUB_TOKEN": "from-env"}  # FAST-HEP tool: no GitLab token is read


def test_load_tokens_without_a_file_uses_only_the_environment(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert tasks_sync.load_tokens(None) == {}


CLOSED = {**ITEM, "number": 94, "title": "Closed issue", "state": "CLOSED"}


def _mirror(tmp_path):
    out = tmp_path / "issues"
    out.mkdir()
    (out / tasks_sync.filename(ITEM)).write_text(tasks_sync.render(ITEM), encoding="utf-8")
    (out / tasks_sync.filename(CLOSED)).write_text(tasks_sync.render(CLOSED), encoding="utf-8")
    (out / "by-hand.md").write_text("my own notes\n", encoding="utf-8")
    return out


def test_prune_dry_run_lists_files_of_closed_issues_and_removes_nothing(tmp_path, monkeypatch, capsys) -> None:
    out = _mirror(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(tasks_sync, "github_items", lambda *a, **k: [ITEM])

    tasks_sync.main(["--out", str(out), "--prune", "--dry-run"])

    printed = capsys.readouterr().out
    assert f"would remove: {out / tasks_sync.filename(CLOSED)}" in printed
    assert tasks_sync.filename(ITEM) not in printed.split("would remove")[-1]
    assert (out / tasks_sync.filename(CLOSED)).exists()


def test_prune_refuses_to_delete_without_a_terminal_and_keeps_hand_written_files(
    tmp_path, monkeypatch, capsys
) -> None:
    out = _mirror(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(tasks_sync, "github_items", lambda *a, **k: [ITEM])
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    tasks_sync.main(["--out", str(out), "--prune"])

    assert "Refusing to prune" in capsys.readouterr().err
    assert (out / tasks_sync.filename(CLOSED)).exists()
    assert (out / "by-hand.md").read_text(encoding="utf-8") == "my own notes\n"


def test_prune_with_typed_confirmation_removes_only_generated_stale_files(tmp_path, monkeypatch) -> None:
    out = _mirror(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(tasks_sync, "github_items", lambda *a, **k: [ITEM])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: "delete")

    tasks_sync.main(["--out", str(out), "--prune"])

    assert not (out / tasks_sync.filename(CLOSED)).exists()
    assert (out / tasks_sync.filename(ITEM)).exists()
    assert (out / "by-hand.md").exists()
