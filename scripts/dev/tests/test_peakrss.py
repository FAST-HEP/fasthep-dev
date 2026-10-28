from __future__ import annotations

import sys

import pytest

from scripts.dev import peakrss


def test_reports_peak_rss_and_wall_time_of_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    rc = peakrss.main([sys.executable, "-c", "x = bytearray(50 * 1024 * 1024); x[::4096] = b'a' * len(x[::4096])"])

    out = capsys.readouterr().out
    assert rc == 0
    line = next(line for line in out.splitlines() if line.startswith("=== PEAK_RSS_MB"))
    fields = line.split()
    assert fields[2].isdigit() and int(fields[2]) >= 50
    assert fields[3] == "WALL_S" and fields[4].isdigit()


def test_passes_the_exit_code_through(capsys: pytest.CaptureFixture[str]) -> None:
    rc = peakrss.main([sys.executable, "-c", "raise SystemExit(3)"])

    assert rc == 3
    assert "=== PEAK_RSS_MB" in capsys.readouterr().out


def test_requires_a_command() -> None:
    with pytest.raises(SystemExit) as exc:
        peakrss.main([])

    assert exc.value.code == 2
