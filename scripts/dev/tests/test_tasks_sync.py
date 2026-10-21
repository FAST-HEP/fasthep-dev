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
