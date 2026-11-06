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
| `dot-github` | `.github` | shared release machinery: git-cliff template, commit convention, changelog contract script, reusable CI workflows |
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

## Compatibility While In Alpha

All FAST-HEP packages are alpha. Beta starts when the full analysis integration (CMS Higgs to
Invisible, `hinv`) is complete; that is still far away.

- Breaking changes are allowed. Do not add deprecation periods, shims or dual formats by default.
- A breaking change must be motivated and documented: the reason in the issue and the PR, the
  break in the changelog (commit message, see each package's `AGENTS.md`), and the changed API or
  file layout in the docs. Say who breaks (workspace consumers) and update them in the same stack.
- Persisted formats still carry a `schema_version`, and it changes with the break. A removed field
  is removed, not left behind.
- Keep a compatibility path only when the issue asks for one, for example because a consumer cannot
  move in the same stack. Name that consumer and the removal step.

## Worktrees For Implementation

- The submodule checkouts in this workspace stay on the repository's default branch, forwarded to
  `origin`, and clean. Do not implement in them.
- Implement each task in its own git worktree under `build/worktrees/<repo>-<slug>`, branched from
  the default branch, for example
  `git -C flow worktree add ../build/worktrees/flow-record-paths -b fix/provenance-record-paths origin/main`.
  A stack of PRs uses one worktree per branch. `build/` is ignored: list ignored files before
  removing a worktree (human gate below).
- The `dev` environment's editable installs point at the workspace checkouts, so a worktree's code
  is not used by default. Put it first on the path:
  `PYTHONPATH=$PWD/build/worktrees/flow-record-paths/src .pixi/envs/dev/bin/python ...`
  (checked for `flow`: the import then resolves to the worktree). Verify with
  `python -c "import hepflow; print(hepflow.__file__)"` before trusting a run. A formal task for
  running tests, workshop tutorials and examples against a worktree is not defined yet.

## Scope, Human Gates And Credentials

- **Scope:** scripts and pixi tasks in this workspace are exclusively for FAST-HEP. `hinv` is
  CMS analysis integration; its scripts and pixi tasks live inside `hinv/chip` (some duplication
  is fine). Workspace tools do not scan, mirror or modify `hinv/`.
- **Human gates:** every destructive or external-write action (deleting build output or
  generated mirrors, pushing branches, removing worktrees) needs a typed confirmation on a
  terminal, is refused without one, and has no flag that skips it. Agents run the dry run, never
  the executing variant (`clean-build-execute`, `push-branches-execute`, `release-notes-backfill-execute`, `--prune`). Every
  HTCondor submit needs explicit approval.
- **Review gates:** two human gates, in this order. (1) The push: the user reviews the diff
  locally and pushes, and a push means that review is done; agents commit locally and never push.
  Agents open the PR only after the push. (2) The PR review before merge; agents never merge
  unless the user asks.
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

## Documentation

User-facing changes to workspace scripts or pixi tasks (new commands, changed behaviour, removed
options) should update the relevant page under `docs/` (for example `docs/scripts.md` for
`scripts/`). This workspace is not released and has no `CHANGELOG.md`.

## Dashboard

`dashboard/app.py` is a human convenience interface for viewing repository
issues, PRs, tags, and CI state. Agents should normally use the authenticated
`gh` CLI for the same information instead of running or modifying the dashboard.

## GitHub And PR Coordination

Use GitHub CLI for issue and PR administration when automation is needed (on lxplus `gh` is not
installed: use the REST and GraphQL APIs with a token from the file the user names for the session). The IDs
of the project, `Status`, `Priority`, `Scope` and `Quarter` are recorded under "Roadmap" below; query any
other field or option before changing it, and never assume an ID that is not recorded.

The FAST-HEP roadmap is:

```text
Owner: FAST-HEP
Project: 3
```

The task lifecycle under "Roadmap" is the standing request to set `Status`, `Priority`, `Scope` and
`Quarter`. Use the other fields (`Difficulty`, `Team`, `Iteration`, `Start date`, `Target date`) only when
explicitly requested. Do not create labels, assign people, merge PRs, retarget branches, or rebase stacks
unless the user asks.

Write issues in the short shape from `FAST-HEP/.github` `docs/issues.md`: a lead paragraph with one number or
example, `## What`, `## Done when`, `## Related`, about 200 words visible and the detail in one collapsed
block. Start from the org default template with `gh issue create --template Task`.

Write pull request bodies in the short shape from `FAST-HEP/.github` `docs/pull-requests.md`: Summary with one
visual, Evidence, Merge Danger and four one-line AI assistance bullets, about 300 words visible and the detail
in one collapsed block. Link the issue and do not restate it. Fetch the skeleton with
`gh api repos/FAST-HEP/.github/contents/.github/PULL_REQUEST_TEMPLATE.md --jq .content | base64 -d`, and use
`gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -F body=@file` to edit an open PR (`gh pr edit` fails on a
deprecated GraphQL field).

For stacked PRs:

- keep each PR to one coherent change;
- target each child PR at the preceding branch;
- include `Depends on: #<PR>` in the child PR description;
- report the full stack order.

For every PR:

- open it only after the user has pushed the branches (the push is the first review gate, so the
  body says the author reviewed the diff before pushing, not "review pending");
- open it ready for review, not as a Draft, when the task is complete; the PR review stays the
  second gate before merge. Use a Draft only for unfinished work the user wants to share early;
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

Directory naming convention (tasks created from 2026-11-06; earlier folders keep their names):

```
tasks/<YYYY-MM-DD>-<target>-<slug>/
```

- `YYYY-MM-DD` is the ISO 8601 creation date (today's date when the task is
  first created).
- `<target>` is where the work lands, by workspace short name: `flow`, `distributed`, `carpenter`,
  `curator`, `render`, `cli`, `toolbench`, `workshop`, `fasthep`, plus `docs` (main-docs), `dev` (this
  workspace), `org` (FAST-HEP/.github) and `chip` (the external analysis). Two or three repositories are
  joined with `+` in alphabetical order (`cli+flow`); more than three is `multi`, and the roadmap node and
  the issue list the repositories.
- `<slug>` is two to five lowercase hyphenated words naming the work. It does not repeat the target. A kind
  word such as `grill` or `handover` is allowed, not required.

Examples: `2026-11-06-flow-site-settings`, `2026-11-06-cli+flow-semantic-diff`,
`2026-11-06-multi-root-file-comparison`. `roadmap-check` warns (never fails) about a new folder that breaks
this; the valid targets are `task_naming` in `tasks/roadmap.yaml`.

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

## Roadmap

`tasks/roadmap.yaml` is the one graph of planned work: nodes with area, size, priority, hard and soft
dependencies, sources and issue URLs. `tasks/ROADMAP.md` is generated from it (ready now, what unblocks
high-priority work, ordered layers) and is read-only. Both are local, like the rest of `tasks/`.

**Placing work.** Before creating a task folder, a task note or an issue, read `tasks/ROADMAP.md` and add or
update its node in `tasks/roadmap.yaml`: `depends_on` for what must come first, `soft_depends_on` for what is
better first, `sources` for the folder, `issue` for the URL. Extend an existing node rather than adding a
duplicate. A seed gets its note and its node now and its issue after the grilling (see the lifecycle). Then run `pixi run --environment scripts roadmap-check` (it fails on a cycle, an unknown id, and any
task folder or mirrored open issue without a node) and `roadmap-write`. Edit the graph, never `ROADMAP.md`.

**Task lifecycle.** The issue is the source of truth for a task, and its project fields are kept current at
each step. Agents do this without being asked and report what they set. They still never merge, push or close
on their own.

1. **Seed:** an idea or a note under `tasks/`. It has a node in the graph (the coverage check requires it) but
   no issue yet. Run it through the grilling skill ("grill-me") first; a seed is not summarised as an issue
   before that.
2. **Grilled:** now there is an up-to-date issue, created in the owning repository and added to project 3. It
   summarises the grilled design, and `Priority`, `Scope` and `Quarter` are set by the rules below. `Status`
   is Backlog. When the design changes, edit the issue.
3. **Implementation plan exists:** `Status` becomes Ready.
4. **Picked up** (a branch or worktree is started): `Status` becomes In progress.
5. **PR opened** (only after the user has pushed): `Status` becomes Review.
6. **PR merged:** `Status` becomes Done.

`Blocked` is set while a hard prerequisite (`depends_on` in the graph) is not done and stops the work; when it
is done, restore the status the task had. Keep the node's `status` in `tasks/roadmap.yaml` in step (Backlog and
Ready are `open`; In progress and Review are `in_progress`; Blocked is `blocked`; Done is `done`), and mark
finished work `done` or `retired`. Add an issue to the project with `gh project item-add 3 --owner FAST-HEP --url <issue-url> --format json`
(the output holds the new item's ID; for an existing item read it from
`gh project item-list 3 --owner FAST-HEP --format json`); set a field with
`gh project item-edit --id <item> --project-id <project> --field-id <field> --single-select-option-id <option>`
(`--iteration-id <period>` for `Quarter`, `--clear` to empty a field).

**Bug reports, and issues filed by others.** The issue may predate any seed. The work still goes through the
same gates, in this order, and everything new is appended to the issue as a comment:

1. **Reproducibility check.** Does the issue say how to reproduce it: steps or a minimal example, versions,
   expected and actual behaviour? If anything is missing, stop at a human gate and ask the maintainer what
   to do next (ask the reporter, investigate, close). Do not decide that yourself.
2. **Fix plan**, then the grilling skill ("grill-me"; bug reports get it too), then the implementation plan
   (`Status` Ready), then the implementation (lifecycle steps 4 to 6).
3. **Place it.** Add the issue to project 3 and a node to the graph, with `Priority`, `Scope` and `Quarter`
   by the rules below, so it follows the same inputs and procedures as work we start ourselves.

**Never overwrite another user's text.** Before editing an issue or a comment, check its author
(`gh issue view <n> --json author`; agents act as the account `gh api user --jq .login` returns). If it is
someone else's, do not edit or delete their issue body or their comments: append a comment instead (the
reproducibility result, the reproduction, the short-shape summary, decisions). Project fields and the graph
node are not their text and are fine to set.

**Project 3 IDs** (https://github.com/orgs/FAST-HEP/projects/3, Monthly and Quarterly roadmap views, grouped
by Team). Check them with `gh project field-list 3 --owner FAST-HEP --format json`; the Quarter periods are
under `ProjectV2IterationField.configuration` in GraphQL. If anything differs, fix this table in the same
change.

| What | ID |
|---|---|
| Project | `PVT_kwDOAhvQf84BgQFw` |
| `Status` field | `PVTSSF_lADOAhvQf84BgQFwzhadIhM` |
| Backlog, Ready, In progress, Done | `f75ad846`, `62b83da8`, `47fc9ee4`, `98236657` |
| Blocked, Review | `5a427125`, `a583dab9` |
| `Priority` field | `PVTSSF_lADOAhvQf84BgQFwzhiQW6Y` |
| P0, P1, P2, P3 | `e79d709d`, `e6736271`, `18904d86`, `37d2f582` |
| `Scope` field | `PVTSSF_lADOAhvQf84BgQFwzhiQW6g` |
| Small, Medium, Large | `f54fc874`, `92449286`, `45adc75a` |
| `Quarter` field | `PVTIF_lADOAhvQf84BgQFwzhadJDs` |
| Quarter 1 (ends 2026-11-10), Quarter 2 (2026-11-11 to 2027-02-08), Quarter 3 (2027-02-09 to 2027-05-09) | `5f6bfd38`, `b64ce631`, `a0844f8e` |

**Setting the fields.** Derive them from the node, and never overwrite a value the maintainer already set.

- `Priority`: high is P1, normal P2, low P3; P0 only if the maintainer names the item urgent. A hard
  prerequisite of a high-priority item inherits P1 (the "Ready now" table shows this).
- `Scope`: S is Small, M Medium, L and XL Large.
- `Quarter`, the only time field used: capacity is 35 effort units per quarter (S 1, M 2, L 4, XL 8). Place an
  item in the earliest quarter with room that is not earlier than the latest Quarter of its hard
  prerequisites; fill in order (high priority and prerequisites first, then earlier layers, smaller first;
  soft dependencies only break ties). Leave it empty when no later period exists yet, when the item is
  deferred, or when it is a backlog tracker. Do not re-plan quarters already set; if a new item overfills one,
  say so. A Quarter is indicative: funding and collaborators are uncertain, so items slip or speed up and the
  quarters are revisited when that changes. Moving an existing value, or re-planning many at once, needs a
  proposed table and the maintainer's approval first.
- `Iteration`, `Start date` and `Target date` are not used (dates would be false precision without funding
  certainty); do not suggest iteration periods. `Team` and `Difficulty` are not derived (Team is set by hand,
  not by repository).

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
