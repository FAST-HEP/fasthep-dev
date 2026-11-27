---
name: maintainability-review
description: Review one FAST-HEP package for duplication, dead code, structure and Hypothesis candidates; diff against the previous run and record the token cost.
disable-model-invocation: true
---

# Maintainability review

One package, one run. The format of every file named here is in `docs/review-format.md`. Read it first.

Inputs: the repository name, the mode (`delta` by default, `full` quarterly or when no previous run exists), and a token budget for `cost.json`.

## Steps

1. **Previous run.** Find the newest `reports/<repo>/*/findings.json`. Done when you hold its commit, or know there is none and the mode is `full`.
2. **Snapshot.** Run `pixi run --environment scripts snapshot --dest build/review --repo <repo>` and show the plan; after the human agrees, add `--execute`. Done when `build/review/<repo>` is at the tip of the default branch.
3. **Tool pass.** Run the package's `pixi run quality` from the snapshot and `pixi run --environment scripts api-surface --repo <repo>`. Keep their output for the agent briefs. Done when both ran, or the reason one cannot run is written in `review.md`.
4. **Scope.** Build `scope.txt` for the mode. Done when it lists every file with a line total and no agent scope exceeds about 4,000 lines.
5. **Agents.** Dispatch one read-only agent per scope in parallel, with the brief from the format document. Done when every agent wrote its `parts/<role>.json`.
6. **Merge.** Combine the parts into `findings.json`, run `review_findings.py stamp`, and drop repeated ids. Verify the ten largest by `est_lines` with grep or a read, and set `verified` on each. Done when `review_findings.py check` passes.
7. **Cost.** Write `cost.json` from the agents' completion notices. Done when `check` prints tokens per finding and no overrun.
8. **Diff.** Run `review_findings.py diff <previous> <this>`. Done when new, resolved, persisting and changed are in `review.md`.
9. **Report.** Render `review.md`: ranked findings by category, the tool output, the diff, the cost. Present the counts and the cost, then stop.

New findings wait for a human triage and the grilling skill before any issue exists. The run changes nothing in the package.
