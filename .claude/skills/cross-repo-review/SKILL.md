---
name: cross-repo-review
description: Review how FAST-HEP packages use each other (private imports, copied helpers, string coupling, version floors) on top of current per-package maintainability reviews.
disable-model-invocation: true
---

# Cross-repo review

Builds on `maintainability-review`. It reads that skill's reports, never repeats them, and looks only at what crosses a package boundary. Formats and the staleness rule are in `docs/review-format.md`. Run it by hand, best before a release.

Inputs: the repositories (default all), the agent model, and a token budget for `cost.json`.

## Steps

0. **Usage before.** Ask the human to note their current usage (5-hour and weekly) and tell you; ask again after the cost is written and record the difference as `usage_share` in `cost.json`. Optional. Done when you hold the figures or the human skipped.

1. **Staleness.** Run `pixi run --environment scripts snapshot --dest build/review` and show the plan; after the human agrees, add `--execute`. Then run `pixi run --environment scripts cross-use stale`. Done when every repository is listed `current` or `STALE` with its reasons.
2. **Offer.** For each `STALE` repository, offer one `maintainability-review` delta run and wait for the answer. Done when each is either reviewed, or the human chose to continue with the old review and `review.md` names it as stale.
3. **Single-repo findings.** Read every repository's newest `findings.json`. Keep those with `risk: cross-package` or a non-empty `consumers`. Done when they are grouped by the sibling they touch.
4. **Tool pass.** Run `api-surface` (private imports, unused public symbols) and `cross-use duplicates`, `strings` and `floors`. Done when the four outputs are saved under `parts/`.
5. **Candidates.** Reduce the tool output to a candidate list: private names imported across packages, helpers with the same name in two repositories (`identical` first), `module:attr` strings that cross or are missing, floors that disagree (`requires-python`, a sibling pin below another repository's pin). Done when each candidate names its files.
6. **Agents.** Dispatch one read-only agent per group of related candidates (for example the persistence stores in carpenter and curator), briefed with the candidate files only and the format document's brief, started with the model named in the input. Done when each wrote `parts/<role>.json`.
7. **Merge.** Combine the parts as in `maintainability-review` step 6 into `reports/_cross/<date>/findings.json`, verify the five largest by grep over the snapshots, then `review_findings.py check`. Done when `check` passes.
8. **Diff and report.** Run `review_findings.py diff` against the previous `_cross` run, write `review.md` (counts, stale repositories, ranked findings, cost) and stop.

Cross-package findings wait for a human triage and the grilling skill before any issue exists. A fix touches several repositories, so each becomes one stack of PRs. This run changes nothing in the packages.
