"""
fasthep-dev dashboard
======================

A tiny, single-file Flask app that gives a quick overview of repos in the
FAST-HEP GitHub org: CI badge, latest tags (calendar-versioned), and open
PR count/links.

Reads from the GitHub REST API. Works with no token (60 req/hour/IP), but
if you set GITHUB_ACCESS_TOKEN (e.g. in a local .env file, a classic PAT
with no scopes needed for public repos), requests are authenticated and
the limit jumps to 5000/hour. A small in-memory TTL cache keeps request
volume down either way.

Run:
    pip install flask requests python-dotenv   # or: pixi add flask requests python-dotenv
    cp .env.example .env   # then fill in GITHUB_ACCESS_TOKEN (optional)
    python app.py
    # then open http://127.0.0.1:5000/?filter=fasthep
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv
from flask import Flask, render_template_string, request

load_dotenv()  # reads .env into os.environ if present; no-op otherwise

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_ACCESS_TOKEN")
ORG = "FAST-HEP"
DEFAULT_FILTER = "fasthep"
DEFAULT_WORKFLOW = "ci.yml"  # matches .github/workflows/ci.yml's filename
PER_PAGE = 100
CACHE_TTL_SECONDS = 300
REQUEST_TIMEOUT = 10

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Tiny in-memory cache to be gentle with the rate limit.
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, object]] = {}


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def cached_get(url: str, params: dict | None = None) -> list | dict:
    key = url + repr(sorted((params or {}).items()))
    now = time.time()
    if key in _cache:
        ts, value = _cache[key]
        if now - ts < CACHE_TTL_SECONDS:
            return value

    resp = requests.get(url, params=params, headers=_headers(), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    _cache[key] = (now, data)
    return data


def get_org_repos(name_prefix: str, include_archived: bool = False) -> list[dict]:
    """Paginate through all public org repos, filtered by name prefix."""
    repos: list[dict] = []
    page = 1
    while True:
        batch = cached_get(
            f"{GITHUB_API}/orgs/{ORG}/repos",
            params={"per_page": PER_PAGE, "page": page, "type": "public"},
        )
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < PER_PAGE:
            break
        page += 1

    if name_prefix:
        repos = [r for r in repos if r["name"].lower().startswith(name_prefix.lower())]
    if not include_archived:
        repos = [r for r in repos if not r.get("archived")]
    return sorted(repos, key=lambda r: r["name"].lower())


def _tag_sort_key(tag_name: str):
    """Sort calendar-versioned tags (e.g. 2026.09.1) numerically, newest first.

    Falls back to plain string comparison for anything that doesn't parse,
    so non-calver tags don't blow up the page.
    """
    parts = re.findall(r"\d+", tag_name)
    if parts:
        return (0, tuple(int(p) for p in parts))
    return (-1, (tag_name,))


def get_tags(repo_name: str, limit: int = 5) -> list[str]:
    tags = cached_get(f"{GITHUB_API}/repos/{ORG}/{repo_name}/tags", params={"per_page": 100})
    names = [t["name"] for t in tags]
    names.sort(key=_tag_sort_key, reverse=True)
    return names[:limit]


def get_open_prs(repo_name: str) -> list[dict]:
    """Return open PRs as [{number, url}], paginating if there are >100."""
    prs: list[dict] = []
    page = 1
    while True:
        batch = cached_get(
            f"{GITHUB_API}/repos/{ORG}/{repo_name}/pulls",
            params={"state": "open", "per_page": 100, "page": page},
        )
        if not batch:
            break
        prs.extend({"number": pr["number"], "url": pr["html_url"]} for pr in batch)
        if len(batch) < 100:
            break
        page += 1
    return prs


def badge_url(repo_name: str, workflow: str) -> str:
    return f"https://github.com/{ORG}/{repo_name}/actions/workflows/{workflow}/badge.svg"


@dataclass
class RepoRow:
    name: str
    html_url: str
    badge: str
    tags: list[str] = field(default_factory=list)
    prs: list[dict] = field(default_factory=list)
    error: str | None = None


TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>FAST-HEP dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; color: #222; }
    h1 { margin-bottom: 0.25rem; }
    form { margin-bottom: 1.5rem; }
    input[type=text] { padding: 0.3rem 0.5rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; vertical-align: top; }
    th { background: #f6f6f6; }
    tr:hover { background: #fafafa; }
    .muted { color: #888; font-size: 0.9em; }
    .tags { font-family: monospace; font-size: 0.9em; }
    code { background: #f2f2f2; padding: 0 0.2rem; }
    .token-status { font-size: 0.85em; padding: 0.2rem 0.5rem; border-radius: 4px; }
    .token-on { background: #e6f4ea; color: #1a7431; }
    .token-off { background: #fdecea; color: #a33; }
  </style>
</head>
<body>
  <h1>FAST-HEP repo dashboard</h1>
  <p class="muted">
    {{ repos|length }} repo(s) matching prefix "{{ filter }}" &middot; cached {{ ttl }}s &middot;
    <span class="token-status {{ 'token-on' if token_set else 'token-off' }}">
      {{ "authenticated (5000 req/hr)" if token_set else "unauthenticated (60 req/hr)" }}
    </span>
  </p>

  <form method="get">
    <label>Filter: <input type="text" name="filter" value="{{ filter }}"></label>
    <label>Workflow file for badge: <input type="text" name="workflow" value="{{ workflow }}"></label>
    <label><input type="checkbox" name="include_archived" {{ "checked" if include_archived }}> Include archived</label>
    <button type="submit">Refresh</button>
  </form>

  <table>
    <thead>
      <tr>
        <th>Repo</th>
        <th>CI</th>
        <th>Latest tags</th>
        <th>Open PRs</th>
      </tr>
    </thead>
    <tbody>
      {% for repo in repos %}
      <tr>
        <td><a href="{{ repo.html_url }}" target="_blank">{{ repo.name }}</a></td>
        <td>
          {% if repo.error %}
            <span class="muted">n/a</span>
          {% else %}
            <a href="{{ repo.html_url }}/actions" target="_blank">
              <img src="{{ repo.badge }}" alt="CI status for {{ repo.name }}">
            </a>
          {% endif %}
        </td>
        <td class="tags">
          {% if repo.tags %}
            {{ repo.tags|join(', ') }}
          {% else %}
            <span class="muted">no tags</span>
          {% endif %}
        </td>
        <td>
          {% if repo.prs %}
            {{ repo.prs|length }} open:
            {% for pr in repo.prs %}
              <a href="{{ pr.url }}" target="_blank">#{{ pr.number }}</a>{{ ", " if not loop.last }}
            {% endfor %}
          {% else %}
            0
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% if error %}
    <p style="color: darkred;">{{ error }}</p>
  {% endif %}
</body>
</html>
"""


@app.route("/")
def dashboard():
    name_filter = request.args.get("filter", DEFAULT_FILTER)
    workflow = request.args.get("workflow", DEFAULT_WORKFLOW)
    include_archived = request.args.get("include_archived") == "on"

    rows: list[RepoRow] = []
    error = None
    try:
        repos = get_org_repos(name_filter, include_archived=include_archived)
    except requests.HTTPError as exc:
        repos = []
        error = f"Failed to list repos: {exc}"

    for repo in repos:
        name = repo["name"]
        row = RepoRow(name=name, html_url=repo["html_url"], badge=badge_url(name, workflow))
        try:
            row.tags = get_tags(name)
            row.prs = get_open_prs(name)
        except requests.HTTPError as exc:
            row.error = str(exc)
        rows.append(row)

    return render_template_string(
        TEMPLATE,
        repos=rows,
        filter=name_filter,
        workflow=workflow,
        ttl=CACHE_TTL_SECONDS,
        token_set=bool(GITHUB_TOKEN),
        include_archived=include_archived,
        error=error,
    )


if __name__ == "__main__":
    app.run(debug=True)
