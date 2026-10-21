# fasthep-dev Agent Instructions

`fasthep-dev` is the FAST-HEP integration workspace. It is not an installable
Python package; it coordinates local checkouts, editable cross-package testing,
release validation, and workspace-level GitHub workflows.

Before changing any subrepository, read the nearest `AGENTS.md` in that
repository. Package-local instructions own package commands, APIs, and coding
conventions.

## Workspace Ownership

This repository owns:

- the shared Pixi development environment;
- checkout and submodule coordination;
- testing unreleased cross-package changes through editable local packages;
- integration and release validation;
- workspace-level GitHub and stacked-PR conventions;
- durable investigation reports under `reports/`.

This repository does not duplicate package architecture, package-local commands,
or package coding rules. Use `fasthep/CONTRIBUTING.md` as the shared
human-facing contribution guide.

## Repository Routing

| Path | Repository | Workspace routing |
|---|---|---|
| `flow` | `fasthep-flow` | compiler, plans, runtime orchestration, backend contracts |
| `distributed` | `fasthep-distributed` | Dask, HTCondor, staging, worker environments, distributed execution |
| `carpenter` | `fasthep-carpenter` | analysis operations, ROOT/awkward I/O, histograms, cutflows |
| `curator` | `fasthep-curator` | dataset inspection, schema snapshots, diagnostics, provenance |
| `render` | `fasthep-render` | plots, reports, rendering styles, graph visualisation |
| `cli` | `fasthep-cli` | `fasthep` command-line interface and user-facing diagnostics |
| `toolbench` | `fasthep-toolbench` | shared utilities, discovery helpers, external-tool adapters |
| `workshop` | `fasthep-workshop` | runnable tutorials, training examples, curated tutorial assets |
| `main-docs` | `fast-hep.github.io` | high-level project portal and package signposting |
| `fasthep` | `fasthep` | metapackage, released dependency bundles, install smoke tests |
| `hinv` | H->invisible migration | CMS analysis integration, separate from FAST-HEP; `hinv/chip` is the evolving full-analysis example; workspace scripts and pixi tasks do not touch it |

Use canonical repository and distribution names in text. Use workspace paths for
local filesystem references.

## Workspace Rules

- Run package-local checks from the owning repository where practical.
- Use the `dev` environment for unreleased cross-package integration.
- Do not run every package, smoke workflow, or tutorial by default.
- Ask which affected tutorials or expensive integration checks should run.
- Preserve dirty submodules and intentional uncommitted work.
- Coordinate cross-package changes as stacked PRs when appropriate.
- Keep source-level integration tests here. Released-installation compatibility
  and import smoke tests may belong in `fasthep`.
- Do not replace package-local release dependencies with workspace paths unless
  explicitly requested.

## Scope, Human Gates And Credentials

- **Scope:** scripts and pixi tasks in this workspace are exclusively for FAST-HEP. `hinv` is
  CMS analysis integration; its scripts and pixi tasks live inside `hinv/chip` (some duplication
  is fine). Workspace tools do not scan, mirror or modify `hinv/`.
- **Human gates:** every destructive or external-write action (deleting build output or
  generated mirrors, pushing branches, removing worktrees) needs a typed confirmation on a
  terminal, is refused without one, and has no flag that skips it. Agents run the dry run, never
  the executing variant (`clean-build-execute`, `push-branches-execute`, `--prune`). PRs are opened
  after the user has pushed. Every HTCondor submit needs explicit approval.
- **Ignored files:** `build/` is gitignored and unprotected, so copy results that matter into
  `reports/`. Mark a folder to keep with an empty `clean.keep` file inside it. Before removing a
  worktree, a `build/` folder or any ignored directory, list what is ignored (`git status
  --ignored`): `git worktree remove` deletes ignored files too.
- **Credentials:** tokens live only in files the user names; the location differs per machine
  (for example `~/private/` on lxplus, a vault folder on a dev machine, one file per service), so
  ask for the location every session and never assume a path. Read them inside the process,
  send them in request headers (not on the command line), and never print, log or write them into
  files, plans, reports, docs or commits. Check scopes with read-only calls first; the user revokes
  them when the work is done.

Useful workspace commands:

```bash
pixi run --environment scripts status
pixi run --environment scripts repo-index
pixi run --environment scripts git-status
pixi run --environment dev smoke-imports
pixi run --environment dev ci
```

`pixi run --environment dev ci` is an editable ecosystem check. It is expensive
relative to package-local checks, so run it only when the change needs
cross-package validation.

## Untracked Files

It is normally safe to ignore files not tracked by Git:

- do not inspect, modify, delete, or report unrelated untracked files;
- preserve untracked files when working in dirty repositories;
- `tasks/` and `reports/` are gitignored in this repository. `reports/` is its own git repository
  (remote on CERN GitLab; the user pushes) and is the exception: it contains durable
  investigation results that may be relevant to refactors or design work. `tasks/` is still to be
  decided.

## Dashboard

`dashboard/app.py` is a human convenience interface for viewing repository
issues, PRs, tags, and CI state. Agents should normally use the authenticated
`gh` CLI for the same information instead of running or modifying the dashboard.

## GitHub And PR Coordination

Use GitHub CLI for issue and PR administration when automation is needed (on lxplus `gh` is not
installed: use the REST and GraphQL APIs with a token from the file the user names for the session). Query
current project fields and option IDs before changing project metadata; do not
store or assume IDs.

The FAST-HEP roadmap is:

```text
Owner: FAST-HEP
Project: 3
```

Use existing project fields such as `Status`, `Priority`, `Difficulty`,
`Scope`, `Iteration`, and `Quarter` only when explicitly requested. Do not
create labels, assign people, merge PRs, retarget branches, or rebase stacks
unless the user asks.

For stacked PRs:

- keep each PR to one coherent change;
- target each child PR at the preceding branch;
- include `Depends on: #<PR>` in the child PR description;
- report the full stack order.

For every PR:

- open it as a Draft; the user pushes the branches, then the PR is opened;
- body: Summary (diagram or tree), Evidence (before and after), Merge Danger (door and blast
  radius), `Depends on:` for the parent, `Refs:` for the tracking issue;
- add the AI-assistance section from `fasthep/CONTRIBUTING.md` and name the model; commits carry
  the Claude `Co-Authored-By` trailer with the model version (existing trailers stay);
- new work items go to the owning repository as issues and onto the FAST-HEP roadmap (project 3)
  without setting fields.

## Agent Task and Roadmap Output

Skills that produce tasks, roadmaps, or structured plans (such as `grilling`,
`mattpocock-skills:grilling`, or similar brainstorming and planning skills)
must write their output under `tasks/` in this workspace.

Directory naming convention:

```
tasks/<YYYY-MM-DD>-<short-slug>/
```

- `YYYY-MM-DD` is the ISO 8601 creation date (today's date when the task is
  first created).
- `<short-slug>` is a brief lowercase hyphenated label describing the task or
  session (e.g. `grill-carpenter-api`, `roadmap-v2`, `hinv-migration-plan`).

Each directory should contain at least one Markdown file summarising the
output. Additional files (checklists, diagrams, notes) may be added alongside.

Do not place task output directly in the workspace root or in `reports/`.
`reports/` is reserved for durable investigation results; `tasks/` is for
agent-generated planning and roadmap artefacts.

Bookkeeping:

- `tasks/INDEX.md` maps each task folder to its issue, PR or MR and status; update it when items
  are created, merged or closed.
- A task note that has an issue starts with `> Tracked in: <URL>`; from then on the issue is the
  source of truth and the note is the original seed.
- `tasks/issues/` is a generated, read-only mirror of the roadmap issues (`tasks-sync`); do not
  edit it.
- `tasks/push-manifest.yaml` lists the FAST-HEP branches `push-branches` shows and pushes.
- Proposed pixi tasks and agent skills are specified in `tasks/2026-10-21-dev-tooling-review/`.

## Release And Scripts

Workspace scripts are catalogued in `docs/scripts.md`. Do not run destructive,
release-tagging, push, submission, or external-write scripts merely to inspect
them. Prefer dry-run commands where provided.

Release validation and tagging are coordinated here, but package content changes
still belong in the owning repository. Treat release scripts as mutating unless
the catalogue says they are read-only or dry-run.

New workspace scripts: FAST-HEP only, dry run by default, a human gate for anything destructive,
tests under `scripts/dev/tests`, and a row in `docs/scripts.md`.

## Environment Notes (lxplus)

- `pixi run` can fail on the AFS lock; the scripts also run with the environment's Python, for
  example `hinv/.pixi/envs/dev/bin/python scripts/dev/clean_build.py`.
- Ports are per node: another user may hold the Dask scheduler port 8786, and only that port is
  reachable from the batch workers. Run from another node (`ssh lxplus.cern.ch`) rather than
  changing the port.
- `fasthep run` compiles again and takes minutes for many remote input files.
- Before a batch run check Kerberos, the proxy lifetime, AFS quota, the scheduler port and your own
  queue; read live worker logs with `condor_tail -stderr` (logs of `condor_rm`'d jobs are lost).
