#!/usr/bin/env python3
"""Run a command and print the peak resident memory and wall time of its process tree.

Usage: peakrss.py COMMAND [ARGS...]

Prints one line after the command ends, ``=== PEAK_RSS_MB <n> WALL_S <n>``, and exits with
the command's exit code. The peak is ``RUSAGE_CHILDREN`` ``ru_maxrss``: the largest resident
set of any single descendant that was waited for, not the sum over processes.

It is a cross-check for the ``hep.resource_usage`` hook of ``fasthep-curator``, which measures
only the partition task, not start-up or the process tree.
"""

from __future__ import annotations

import resource
import subprocess
import sys
import time


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: peakrss.py COMMAND [ARGS...]", file=sys.stderr)
        raise SystemExit(2)
    start = time.time()
    returncode = subprocess.call(argv)
    # ru_maxrss is in kilobytes on Linux.
    peak_mb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    print(f"=== PEAK_RSS_MB {peak_mb:.0f} WALL_S {time.time() - start:.0f}")
    return returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
