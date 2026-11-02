from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def passing_changelog_tool(tmp_path_factory, monkeypatch) -> None:
    """Stand-in for the FAST-HEP/.github changelog tool whose contract check always passes."""
    tools = tmp_path_factory.mktemp("tools")
    (tools / "scripts").mkdir()
    Path(tools / "scripts" / "fasthep_changelog.py").write_text("import sys\nsys.exit(0)\n")
    monkeypatch.setenv("FASTHEP_DOTGITHUB", str(tools))
