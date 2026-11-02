# Release path: commits to published notes

One rule drives the path: **a new version means real changes.** Commits are the single source;
the changelog section and the GitHub Release notes are generated from them and never edited by
hand. The logic is forge-neutral Python and `git-cliff` in the shared repository
[FAST-HEP/.github](https://github.com/FAST-HEP/.github) (rules: its `docs/commit-convention.md`);
the pixi tasks here and the GitHub workflows there are thin wrappers around the same script.

```
commit (convention)  ->  release-changelog  ->  tag  ->  CD: contract -> PyPI -> GitHub Release
   hook + CI check        git-cliff section       gate        (per package, on the tag push)
```

## Setup

The workspace uses a local checkout of the shared repository (read-only for these tasks):

```bash
git clone https://github.com/FAST-HEP/.github external/dot-github
```

`FASTHEP_DOTGITHUB` points elsewhere if you keep it in another place. `git-cliff` and `gh` come
with the `scripts` pixi environment.

## The steps

| # | Step | Command | What it checks or does |
|---|---|---|---|
| 1 | Write commits | commit-msg hook, CI `commit-check` | Subject is `<type>(<scope>): <description>`; the subject becomes the changelog bullet; `Changelog:` trailer is valid |
| 2 | Bump `releases.json` | by hand | A package with no visible commit since its tag stays at its tagged version |
| 3 | Draft the changelogs | `release-changelog-dry`, then `release-changelog` | For each package whose version is not tagged yet: git-cliff drafts `## [X] - <date>` from the commits since its last tag and inserts it under the empty `## [Unreleased]`; refuses if a package has no visible commit; writes nothing unless every package drafts; commits `docs(changelog): add X release` locally. Tagged packages with visible commits get a hint to bump them |
| 4 | Review, push, merge | normal PR flow | Human review gate. The changelog commit must be on the branch that is tagged |
| 5 | Check the contract | `release-check-changelog` | Every package has a dated, non-empty `## [X]` and an empty `## [Unreleased]`; `fasthep`'s block equals the aggregate of the packages |
| 6 | Tag | `release-tag-dry`, `release-tag`, `release-tag-push` | Refuses the whole batch before tagging anything if a package about to be tagged fails the contract |
| 7 | CD (on the tag push) | per package `cd.yml` | `changelog-contract` fails before anything is published; then PyPI; then `github-release` |
| 8 | `fasthep` | `release-aggregate-changelog`, then tag | Its changelog is the aggregate of the package sections; its release notes are that block |

The existing procedure in the README (workshop and `fasthep` pinned last, validation, pins) is
unchanged; step 3 above is step 2a there, and the contract check is repeated by `tag_packages.py`
for each tag.

## What each gate checks

| Gate | Where | Fails when |
|---|---|---|
| commit-msg hook | each repo, local | subject or `Changelog:` trailer breaks the convention |
| `commit-check` | each repo, CI on pull requests | any commit in the PR breaks it (also `fixup!`/`squash!`) |
| `release-changelog` | here | a package to release has no visible commit since its tag; `[Unreleased]` is not empty; git-cliff fails |
| `tag_packages.py` | here | a package to tag has no `## [X]` section, no date, no entries, or a non-empty `[Unreleased]` |
| `changelog-contract` | each repo, CD | the same, on the pushed tag; stops before PyPI |
| `github-release` | each repo, CD | `gh` fails; a re-run edits the existing release instead of failing |

A failed contract in CD publishes nothing: fix the changelog, delete the tag, tag again.

## Backfill of old tags

Tags that predate the release job have no GitHub Release. The backfill creates them from each
package's own `## [X]` section, plus the PyPI link:

```bash
pixi run --environment scripts release-notes-backfill-dry      # list only (reads releases via gh)
pixi run --environment scripts release-notes-backfill-execute  # human gate: typed confirmation
```

It starts at `2026.10.0` (`--since`), skips tags that have a release, lists tags without a
changelog section instead of inventing notes, and marks only each repository's newest tag as latest.
Publishing is public and shows up in watchers' feeds, so the executing variant needs a typed
`release` on a terminal and refuses without one. `gh` uses its own login or the `GH_TOKEN` you set
from the token file you name for the session; the script never reads or prints a token.

## Fixing things in one place

The template (`cliff.toml`), the commit rules, the contract and the release notes format live only
in FAST-HEP/.github, so a fix there reaches every package. The flip side: callers reference
`@main`, so a bad change reaches all nine at once. Pin the callers to a tag of FAST-HEP/.github
once the rules are stable.
