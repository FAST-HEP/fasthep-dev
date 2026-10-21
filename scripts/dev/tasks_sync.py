#!/usr/bin/env python3
"""Mirror open GitHub issues of the FAST-HEP roadmap project into ``tasks/issues/``.

FAST-HEP only (the chip GitLab issues are mirrored by the copy of this tool in ``hinv/chip``).
Read-only towards GitHub; the only writes are local files below
``tasks/issues/``. A file is overwritten only if it carries ``generated-by: tasks-sync``,
so notes written by hand are never touched. ``--prune`` removes generated files whose
issue is no longer in the selection (closed, or removed from the project); like every deletion
it is a human gate (typed confirmation on a terminal, refused without one).

Credentials: ``GITHUB_TOKEN`` from the environment, else from an env
file given with ``--env-file`` or ``FASTHEP_ENV_FILE`` (lines ``NAME=value``; the location differs
per machine, ask the owner for it each session). Tokens are only sent as
request headers and are never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MARKER = "generated-by: tasks-sync"
GH_QUERY = """
query($org: String!, $number: Int!, $after: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      title
      items(first: 50, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          content {
            __typename
            ... on Issue { number title body state url updatedAt repository { nameWithOwner } labels(first: 10) { nodes { name } } }
            ... on PullRequest { number title body state url updatedAt repository { nameWithOwner } labels(first: 10) { nodes { name } } }
            ... on DraftIssue { title body }
          }
        }
      }
    }
  }
}
"""


def load_tokens(env_file: Path | None) -> dict[str, str]:
    tokens = {k: os.environ[k] for k in ("GITHUB_TOKEN",) if os.environ.get(k)}
    if env_file is not None and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)$", line)
            if match and match.group(1) == "GITHUB_TOKEN":
                tokens.setdefault(match.group(1), match.group(2).strip().strip("\"'"))
    return tokens


def request(url: str, headers: dict[str, str], body: dict | None = None) -> tuple[dict | list, dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "fasthep-dev-tasks-sync", **headers})
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode() or "null"), dict(response.headers)
    except urllib.error.HTTPError as exc:  # never include headers (they hold the token)
        raise SystemExit(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}{urllib.parse.urlsplit(url).path}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from None


def github_items(token: str, org: str, number: int, *, include_closed: bool) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    items, after = [], None
    while True:
        payload, _ = request("https://api.github.com/graphql", headers,
                             {"query": GH_QUERY, "variables": {"org": org, "number": number, "after": after}})
        if payload.get("errors"):
            raise SystemExit("GitHub GraphQL error: " + "; ".join(e.get("message", "?") for e in payload["errors"])[:200])
        project = payload["data"]["organization"]["projectV2"]
        page = project["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            kind = content.get("__typename")
            if kind not in ("Issue", "PullRequest"):
                continue
            if content["state"] != "OPEN" and not include_closed:
                continue
            items.append({
                "source": "github", "repository": content["repository"]["nameWithOwner"],
                "number": content["number"], "kind": kind.lower(), "title": content["title"],
                "body": content.get("body") or "", "state": content["state"], "url": content["url"],
                "updated": content["updatedAt"], "status": (node.get("fieldValueByName") or {}).get("name", ""),
                "labels": [label["name"] for label in content["labels"]["nodes"]],
            })
        if not page["pageInfo"]["hasNextPage"]:
            return items
        after = page["pageInfo"]["endCursor"]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "item"


def filename(item: dict) -> str:
    repo = item["repository"].split("/")[-1]
    return f"{item['source']}-{repo}-{item['number']}-{slug(item['title'])}.md"


def render(item: dict) -> str:
    labels = ", ".join(item["labels"])
    front = (f"---\nsource: {item['source']}\nrepository: {item['repository']}\nnumber: {item['number']}\n"
             f"kind: {item['kind']}\nurl: {item['url']}\nstate: {item['state']}\nproject-status: {item['status']}\n"
             f"labels: [{labels}]\nupdated: {item['updated']}\n{MARKER}\n---\n")
    return f"{front}# {item['title']}\n\n{item['body'].strip()}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("tasks/issues"))
    parser.add_argument("--env-file", type=Path, default=Path(os.environ["FASTHEP_ENV_FILE"]) if os.environ.get("FASTHEP_ENV_FILE") else None,
                        help="file with GITHUB_TOKEN=... (default: $FASTHEP_ENV_FILE; location differs per machine)")
    parser.add_argument("--github-org", default="FAST-HEP")
    parser.add_argument("--github-project", type=int, default=3)
    parser.add_argument("--include-closed", action="store_true")
    parser.add_argument("--prune", action="store_true", help="remove generated files no longer in the selection")
    parser.add_argument("--dry-run", action="store_true", help="show what would be written")
    args = parser.parse_args(argv)

    tokens = load_tokens(args.env_file)
    if "GITHUB_TOKEN" not in tokens:
        raise SystemExit("GITHUB_TOKEN not set: export it, set FASTHEP_ENV_FILE or pass --env-file PATH (ask the owner where the token file is)")
    items = github_items(tokens["GITHUB_TOKEN"], args.github_org, args.github_project, include_closed=args.include_closed)

    out = args.out
    wanted = {filename(item): item for item in items}
    existing = {p.name: p for p in out.glob("*.md")} if out.is_dir() else {}
    written = skipped = 0
    for name, item in sorted(wanted.items()):
        path = out / name
        if path.exists() and MARKER not in path.read_text(encoding="utf-8"):
            print(f"skip (hand-written file in the way): {path}")
            skipped += 1
            continue
        print(f"{'would write' if args.dry_run else 'write'}: {path}")
        if not args.dry_run:
            out.mkdir(parents=True, exist_ok=True)
            path.write_text(render(item), encoding="utf-8")
        written += 1
    pruned = 0
    if args.prune:
        stale = [p for n, p in existing.items()
                 if n not in wanted and n != "INDEX.md" and MARKER in p.read_text(encoding="utf-8")]
        for path in stale:
            print(f"{'would remove' if args.dry_run else 'remove'}: {path}")
        if stale and not args.dry_run:
            if not sys.stdin.isatty():
                print("Refusing to prune: no terminal to confirm on (deleting is a human gate).", file=sys.stderr)
            elif input(f"Type 'delete' to remove {len(stale)} stale generated files: ").strip() == "delete":
                for path in stale:
                    path.unlink()
                pruned = len(stale)
    if not args.dry_run and wanted:
        rows = ["| Item | Title | State | Project status |", "|---|---|---|---|"]
        for name, item in sorted(wanted.items()):
            rows.append(f"| [{item['repository'].split('/')[-1]}#{item['number']}]({item['url']}) | {item['title']} | {item['state']} | {item['status']} |")
        (out / "INDEX.md").write_text(
            "# Issues mirrored from the FAST-HEP roadmap project\n\nGenerated by `scripts/dev/tasks_sync.py` "
            "(read-only mirror; do not edit, edit the issue).\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"\n{len(items)} items fetched; {written} {'to write' if args.dry_run else 'written'}, {skipped} skipped, {pruned} pruned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
