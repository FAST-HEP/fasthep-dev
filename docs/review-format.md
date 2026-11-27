# Maintainability review: run format

Shared reference for the `maintainability-review` skill (one repository) and the multi-repository skill built on it.
Nothing here names a package: the repository, its package and its layout come from the run.

## Run directory

`reports/<repo>/<YYYY-MM-DD>/` in the durable `reports/` repository:

| File | Content |
|---|---|
| `findings.json` | the findings, with fingerprint ids |
| `cost.json` | tokens, tool calls and duration per agent |
| `review.md` | the rendered page: ranked findings, tool output, what changed since the previous run |
| `scope.txt` | the files read, one per line, with a line total |
| `parts/` | one raw fragment per agent |

## findings.json

`{"schema_version": 1, "repo", "commit", "mode": "full|delta", "since": "<commit or null>", "date", "findings": [...]}`

| Field | Meaning |
|---|---|
| `id` | fingerprint of `category`, `file`, `symbol`, `key`; written by `review_findings.py stamp`, never by hand |
| `category` | `duplication`, `dead`, `structure`, `hypothesis` or `cross-use` |
| `file`, `symbol` | where, by name; `symbol` is the function or class, empty for a whole file |
| `key` | optional short slug that separates two findings on the same symbol |
| `line` | informational; not part of the id |
| `summary`, `proposal` | what is wrong, and the change that fixes it |
| `est_lines` | net lines, negative when removed; an estimate |
| `risk` | `none`, `in-repo` or `cross-package` |
| `consumers` | sibling packages that would break, from grep evidence |
| `verified` | `true` once a grep or a read confirmed it on the snapshot, else `false` |

An id survives moves and edits around the symbol. Renaming the symbol or moving the file makes the finding `new` and the old one `resolved`; that is accepted.

## cost.json

`{"schema_version": 1, "repo", "commit", "mode", "budget_tokens", "main_session_tokens": null, "agents": [{"role", "tokens", "tool_uses", "duration_ms", "findings", "lines_in_scope"}]}`

The numbers come from each subagent's completion notice. The main session's own tokens are not exposed by the harness, so `main_session_tokens` stays `null`. `review_findings.py check` prints tokens per finding and per 1,000 lines and fails on an overrun of `budget_tokens`.

## Scope

- **full:** every file under the package source and tests.
- **delta:** files changed since the previous run's commit (`git diff --name-only <since>..<commit>`), plus the files that import them. If the previous run is missing or older than 90 days, run full.
- **Agent split:** by subpackage, at most about 4,000 lines per agent; tests get their own agents.

## Agent brief (fill the placeholders, keep the rest)

> Read-only review of `<package>` at `<snapshot>` (read its AGENTS.md first). Scope: `<files>`. Tool output already known: `<quality and api-surface output>`; do not rediscover it. Report in the finding fields above as JSON to `<run>/parts/<role>.json`, without ids. Flag duplicated logic, thin wrappers and dead code (verify with grep over the package, its tests and the sibling snapshots, and name who would break), hand-rolled code the standard library covers, oversized units and misleading names. Tests: where `hypothesis` shortens a property, and repeated fixtures or builders. Alpha project: propose breaking changes plainly, with no shims. Final reply: under 150 words.

## Prior art

CodeChecker's `diff` (new, resolved, unresolved by a report hash), GitHub code scanning's SARIF fingerprints (a stable `ruleId` and consistent paths), and review bots that skip an unchanged commit and review the delta. None covers agent findings with a token cost, so this is a thin layer using their vocabulary. SARIF export is a later option: `id` maps to `partialFingerprints`.
