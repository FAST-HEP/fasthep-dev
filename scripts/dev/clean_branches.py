#!/usr/bin/env python3
"""List and, on request, delete branches that are already merged, in each FAST-HEP repository.

Local and ``origin`` branches are treated the same: one row per branch name, whichever side(s) it
exists on. A branch is suggested for deletion when

* its tip is contained in ``origin/<default>`` (merge-commit and fast-forward merges), or
* its pull request is merged and the tip equals the pull request head (squash and rebase merges;
  needs ``--token-file``).

It is kept when it has an open pull request, commits that are in no merged pull request, is
checked out in a worktree (a stale, prunable worktree does not count), or matches ``--protect``
(default ``legacy``, ``backup*``, ``gh-pages``, ``release/*``: long-lived branches that are merged
by accident of history). The default branch is never listed.

The default is a read-only list (after ``git fetch``; ``--no-fetch`` skips it) that also prints the
commands for the suggested deletions. ``--execute`` asks ``delete? [y/N]`` for each suggested branch
and deletes the local branch and the ``origin`` branch it names. This is a human gate: it needs a
terminal, is refused without one, and has no option to skip it. A remote branch is only deleted if
its tip is still the one that was listed.

Credentials: ``--token-file`` names a ``KEY=value`` file with ``GITHUB_TOKEN`` (the location differs
per machine, so it has no default). The token is read inside this process, sent only in the
``Authorization`` header of read-only pull request queries, and never printed. Deleting uses git.

FAST-HEP only: ``hinv/`` is not touched.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPOS = (
    "flow", "distributed", "carpenter", "curator", "render", "cli",
    "toolbench", "workshop", "dot-github", "main-docs", "fasthep",
)
PROTECTED = ("legacy", "backup*", "gh-pages", "release/*")
COLUMNS = ("REPO", "BRANCH", "WHERE", "TIP", "AHEAD", "PR", "STATE")
LEGEND = """\
Columns:
  REPO    workspace checkout
  BRANCH  branch name (local and origin branches of the same name share a row)
  WHERE   local, remote or both
  TIP     short commit id of the branch tip
  AHEAD   commits of the tip that origin/<default> does not have (? if the commit is not fetched)
  PR      pull request of that branch: #number and open or merged (needs --token-file)
States:
  merged              tip is in origin/<default>: suggest delete
  PR merged           pull request merged with this very tip (squash or rebase): suggest delete
  KEEP: open PR       pull request still open
  KEEP: unmerged      commits that are in no merged pull request
  KEEP: worktree      checked out in a worktree (remove the worktree first)
  KEEP: protected     matches --protect (legacy, backup*, gh-pages, release/* by default)
  KEEP: PR merged, newer commits   commits were added after the pull request merged"""


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


@dataclass
class Branch:
    repo: str
    path: Path
    name: str
    local: str = ""
    remote: str = ""
    ahead: str = "?"
    merged: bool = False
    pr: dict | None = None
    worktree: str = ""
    state: str = ""
    deletable: bool = False
    squash_proven: bool = False

    @property
    def where(self) -> str:
        return "both" if self.local and self.remote else ("local" if self.local else "remote")

    @property
    def tip(self) -> str:
        return self.local or self.remote


def read_token(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() in ("GITHUB_TOKEN", "GH_TOKEN") and value.strip():
            return value.strip().strip("'\"")
    raise SystemExit(f"{path}: no GITHUB_TOKEN entry")


def slug_of(repo: Path) -> str | None:
    url = git(repo, "remote", "get-url", "origin", check=False).stdout.strip()
    found = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return found.group(1) if found else None


def fetch_prs(slug: str, token: str, *, pages: int = 5) -> dict[str, dict]:
    """Pull requests of ``slug`` by head branch name (same-repo heads only; newest wins)."""
    found: dict[str, dict] = {}
    for page in range(1, pages + 1):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{slug}/pulls?state=all&per_page=100&page={page}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "fasthep-dev-clean-branches",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            items = json.load(response)
        for item in items:
            head = item.get("head") or {}
            if (head.get("repo") or {}).get("full_name") != slug:
                continue
            state = "merged" if item.get("merged_at") else item.get("state", "?")
            found.setdefault(head["ref"], {"number": item["number"], "state": state, "sha": head["sha"]})
        if len(items) < 100:
            break
    return found


def default_branch(repo: Path) -> str:
    ref = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False).stdout.strip()
    return ref.removeprefix("refs/remotes/") if ref else "origin/main"


def worktree_branches(repo: Path) -> dict[str, str]:
    out = git(repo, "worktree", "list", "--porcelain", check=False).stdout
    used: dict[str, str] = {}
    for block in out.split("\n\n"):
        lines = block.splitlines()
        if any(line.startswith("prunable") for line in lines):
            continue  # registration of a worktree that no longer exists
        path = next((l.removeprefix("worktree ") for l in lines if l.startswith("worktree ")), "")
        for line in lines:
            if line.startswith("branch refs/heads/"):
                used[line.removeprefix("branch refs/heads/")] = Path(path).name
    return used


def collect(
    repo: Path, name: str, *, fetch: bool, prs: dict[str, dict], protect: tuple[str, ...] = PROTECTED
) -> list[Branch]:
    if fetch:
        git(repo, "fetch", "--quiet", "origin", check=False)
    default = default_branch(repo)
    default_short = default.removeprefix("origin/")
    branches: dict[str, Branch] = {}
    for line in git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads").stdout.splitlines():
        ref, _, sha = line.partition(" ")
        branches[ref] = Branch(name, repo, ref, local=sha)
    remote = git(repo, "ls-remote", "--heads", "origin", check=False)
    for line in remote.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        ref = ref.removeprefix("refs/heads/")
        branches.setdefault(ref, Branch(name, repo, ref)).remote = sha
    branches.pop(default_short, None)
    used = worktree_branches(repo)
    result = []
    for branch in sorted(branches.values(), key=lambda b: b.name):
        branch.worktree = used.get(branch.name, "")
        branch.pr = prs.get(branch.name)
        have = git(repo, "cat-file", "-e", f"{branch.tip}^{{commit}}", check=False).returncode == 0
        if have:
            ahead = git(repo, "rev-list", "--count", f"{default}..{branch.tip}", check=False).stdout.strip()
            branch.ahead = ahead or "?"
            branch.merged = git(repo, "merge-base", "--is-ancestor", branch.tip, default, check=False).returncode == 0
        classify(branch)
        if branch.deletable and any(fnmatch.fnmatch(branch.name, g) for g in protect):
            branch.state, branch.deletable = "KEEP: protected", False
        result.append(branch)
    return result


def classify(branch: Branch) -> None:
    pr = branch.pr
    if branch.merged:
        branch.state, branch.deletable = "merged", True
    elif pr and pr["state"] == "merged" and pr["sha"] == branch.tip:
        branch.state, branch.deletable, branch.squash_proven = "PR merged", True, True
    elif pr and pr["state"] == "open":
        branch.state = "KEEP: open PR"
    elif pr and pr["state"] == "merged":
        branch.state = "KEEP: PR merged, newer commits"
    else:
        branch.state = "KEEP: unmerged"
    if branch.deletable and branch.worktree and branch.local:
        branch.state, branch.deletable = f"KEEP: worktree {branch.worktree}", False


def row(branch: Branch) -> tuple[str, ...]:
    pr = f"#{branch.pr['number']} {branch.pr['state']}" if branch.pr else ""
    return (branch.repo, branch.name, branch.where, branch.tip[:7], branch.ahead, pr, branch.state)


def table(branches: list[Branch]) -> str:
    rows = [COLUMNS, *(row(b) for b in branches)]
    widths = [max(len(r[i]) for r in rows) for i in range(len(COLUMNS))]
    lines = []
    for n, r in enumerate(rows):
        cells = [c.rjust(widths[i]) if COLUMNS[i] == "AHEAD" else c.ljust(widths[i]) for i, c in enumerate(r)]
        lines.append("  ".join(cells).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def commands(branch: Branch) -> list[str]:
    out = []
    if branch.local:
        out.append(f"git -C {branch.path} branch {'-D' if branch.squash_proven else '-d'} {branch.name}")
    if branch.remote:
        out.append(f"git -C {branch.path} push origin --delete {branch.name}")
    return out


def delete(branch: Branch) -> bool:
    ok = True
    if branch.remote:
        live = git(branch.path, "ls-remote", "--heads", "origin", branch.name, check=False).stdout.split("\t")[0]
        if live != branch.remote:
            print(f"  remote {branch.name} moved or is gone since listing; not deleted", file=sys.stderr)
            ok = False
        else:
            done = git(branch.path, "push", "--quiet", "origin", "--delete", branch.name, check=False)
            if done.returncode != 0:
                print(f"  remote delete failed: {done.stderr.strip()}", file=sys.stderr)
                ok = False
            else:
                print(f"  deleted origin/{branch.name}")
    if branch.local:
        done = git(branch.path, "branch", "-D" if branch.squash_proven else "-d", branch.name, check=False)
        if done.returncode != 0:
            print(f"  local delete failed: {done.stderr.strip()}", file=sys.stderr)
            ok = False
        else:
            print(f"  deleted local {branch.name}")
    return ok


def main(argv: list[str] | None = None, ask=input) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="workspace root (default: cwd)")
    parser.add_argument("--repo", action="append", metavar="NAME", help="only this checkout (repeatable)")
    parser.add_argument("--token-file", type=Path, help="KEY=value file with GITHUB_TOKEN, for pull request state")
    parser.add_argument("--protect", action="append", metavar="GLOB", help=f"never suggest branches matching GLOB (default: {', '.join(PROTECTED)}; repeatable, replaces the default)")
    parser.add_argument("--no-fetch", action="store_true", help="do not run git fetch first")
    parser.add_argument("--execute", action="store_true", help="ask per suggested branch and delete (default: list only)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    token = read_token(args.token_file) if args.token_file else None
    all_branches: list[Branch] = []
    for name in args.repo or REPOS:
        repo = root / name
        if not (repo / ".git").exists():
            print(f"skipping {name}: not a checkout under {root}", file=sys.stderr)
            continue
        prs: dict[str, dict] = {}
        slug = slug_of(repo)
        if token and slug:
            try:
                prs = fetch_prs(slug, token)
            except OSError as error:
                print(f"{name}: pull requests unavailable ({error.__class__.__name__}); using git only", file=sys.stderr)
        all_branches.extend(collect(repo, name, fetch=not args.no_fetch, prs=prs, protect=tuple(args.protect or PROTECTED)))

    if all_branches:
        print(table(all_branches))
        print()
        print(LEGEND)
    suggested = [b for b in all_branches if b.deletable]
    print(f"\n{len(all_branches)} branches, {len(suggested)} suggested for deletion")
    if not args.execute:
        if suggested:
            print("\nCommands for the suggested deletions (not run):")
            for branch in suggested:
                for command in commands(branch):
                    print(f"  {command}")
        print("\nNothing deleted (dry run). Add --execute to be asked per branch.")
        return 0
    if not suggested:
        print("Nothing to ask about.")
        return 0
    if not sys.stdin.isatty():
        print("Refusing: no terminal to confirm on (deleting is a human gate).", file=sys.stderr)
        return 2
    deleted = 0
    for branch in suggested:
        reply = ask(f"delete {branch.repo} {branch.name} ({branch.where}, {branch.state}, tip {branch.tip[:7]})? [y/N] ")
        if reply.strip().lower() == "y" and delete(branch):
            deleted += 1
    print(f"\n{deleted} deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
