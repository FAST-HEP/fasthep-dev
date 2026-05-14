#!/usr/bin/env python3

from pathlib import Path
import subprocess

root = Path.cwd()

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def plural(n: int, singular: str, plural_: str | None = None) -> str:
    if n == 1:
        return f"1 {singular}"
    return f"{n} {plural_ or singular + 's'}"


def get_ahead_behind(repo: Path) -> str:
    result = run_git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")

    if result.returncode != 0:
        return "no upstream"

    ahead, behind = map(int, result.stdout.split())

    if ahead == 0 and behind == 0:
        return "up to date"

    parts = []
    if ahead:
        parts.append(f"ahead {ahead}")
    if behind:
        parts.append(f"behind {behind}")

    return ", ".join(parts)


repos = sorted(git_dir.parent for git_dir in root.glob("*/.git"))

name_width = max((len(repo.name) for repo in repos), default=0)
status_width = 34

for repo in repos:
    result = run_git(repo, "status", "--porcelain")

    if result.returncode != 0:
        print(f"{RED}{repo.name:<{name_width}}  error: {result.stderr.strip()}{RESET}")
        continue

    lines = [line for line in result.stdout.splitlines() if line.strip()]

    tracked = sum(1 for line in lines if not line.startswith("??"))
    untracked = sum(1 for line in lines if line.startswith("??"))

    if tracked == 0 and untracked == 0:
        colour = GREEN
        status = "no changes"
    else:
        parts = []

        if tracked:
            parts.append(plural(tracked, "pending file"))

        if untracked:
            parts.append(plural(untracked, "untracked file"))

        status = " / ".join(parts)
        colour = RED if tracked else YELLOW

    sync = get_ahead_behind(repo)

    if sync == "no upstream":
        sync = f"{DIM}{sync}{RESET}"

    print(
        f"{colour}{repo.name:<{name_width}}{RESET}  "
        f"{colour}{status:<{status_width}}{RESET}  "
        f"{sync}"
    )