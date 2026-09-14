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
| `hinv` | H->invisible migration | migration repository; `hinv/chip` is the evolving full-analysis example |

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
- `reports/` is the exception: it contains durable investigation results that
  may be relevant to refactors or design work.

## Dashboard

`dashboard/app.py` is a human convenience interface for viewing repository
issues, PRs, tags, and CI state. Agents should normally use the authenticated
`gh` CLI for the same information instead of running or modifying the dashboard.

## GitHub And PR Coordination

Use GitHub CLI for issue and PR administration when automation is needed. Query
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

## Release And Scripts

Workspace scripts are catalogued in `docs/scripts.md`. Do not run destructive,
release-tagging, push, submission, or external-write scripts merely to inspect
them. Prefer dry-run commands where provided.

Release validation and tagging are coordinated here, but package content changes
still belong in the owning repository. Treat release scripts as mutating unless
the catalogue says they are read-only or dry-run.
