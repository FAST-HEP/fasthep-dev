"""Glue to the shared changelog tool in FAST-HEP/.github (``scripts/fasthep_changelog.py``).

The tool and its ``cliff.toml`` live in a local checkout of that repository, by default
``dot-github`` (override with ``FASTHEP_DOTGITHUB``). It is called through its command
line, the same one CI uses, so a rule only has to be fixed there.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS_ENV = "FASTHEP_DOTGITHUB"
DEFAULT_TOOLS_DIR = Path("dot-github")
CLONE_HINT = "git submodule update --init dot-github"


class ToolFailure(Exception):
    """The shared tool refused; the message is its own explanation."""


def tools_script(root: Path) -> Path:
    base = Path(os.environ.get(TOOLS_ENV) or root / DEFAULT_TOOLS_DIR)
    script = base / "scripts" / "fasthep_changelog.py"
    if not script.exists():
        raise SystemExit(
            f"changelog tool not found at {script}\n"
            f"  get it:  {CLONE_HINT}\n  or set {TOOLS_ENV} to a checkout of FAST-HEP/.github"
        )
    return script


def _run(root: Path, *args: str, cwd: Path | None = None, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(tools_script(root)), *args],
        cwd=cwd,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def _message(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr.strip() or result.stdout.strip() or "no output").replace("\n", "\n    ")


def check_contract(root: Path, changelog: Path, version: str) -> list[str]:
    """Problems with ``changelog`` for a release ``version`` (empty list: the contract holds)."""
    if not changelog.exists():
        return [f"{changelog} does not exist"]
    result = _run(root, "check", str(changelog), version)
    if result.returncode == 0:
        return []
    return [line.strip() for line in result.stderr.splitlines() if line.strip()] or [
        _message(result)
    ]


def draft_section(root: Path, repo: Path, version: str) -> str:
    """The cliff section for the commits since ``repo``'s last tag."""
    result = _run(root, "draft", version, "--repo", str(repo), cwd=repo)
    if result.returncode != 0:
        raise ToolFailure(_message(result))
    return result.stdout


def insert_section(root: Path, changelog: Path, version: str, section: str) -> str:
    """``changelog`` with ``section`` under ``## [Unreleased]``; nothing is written to it."""
    # The tool's dry run does not print the result, so let it write a scratch copy.
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "CHANGELOG.md"
        scratch.write_text(changelog.read_text(encoding="utf-8"), encoding="utf-8")
        result = _run(root, "insert", str(scratch), version, "--write", stdin=section)
        if result.returncode != 0:
            raise ToolFailure(_message(result))
        return scratch.read_text(encoding="utf-8")


def release_notes(root: Path, changelog: Path, version: str, pypi_name: str | None) -> str:
    args = ["release-notes", str(changelog), version]
    if pypi_name:
        args += ["--pypi", pypi_name]
    result = _run(root, *args)
    if result.returncode != 0:
        raise ToolFailure(_message(result))
    return result.stdout
