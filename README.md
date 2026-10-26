# fasthep-dev

Development and integration workspace for the FAST-HEP ecosystem.

This repository is **not** an installable Python package. It collects the FAST-HEP repositories as Git submodules and provides shared tooling for development, testing, and release validation.

## Clone

This workspace uses SSH Git submodule URLs by default.

```bash
git clone --recurse-submodules git@github.com:FAST-HEP/fasthep-dev.git
cd fasthep-dev
```

If submodules are missing:

```bash
git submodule update --init --recursive
```

## Repositories

| Local path | Canonical repository/package | Purpose |
|---|---|---|
| `fasthep` | `fasthep` | meta package and verified compatibility bundle |
| `flow` | `fasthep-flow` | workflow compilation, planning, and orchestration |
| `carpenter` | `fasthep-carpenter` | HEP analysis transforms and histogramming |
| `curator` | `fasthep-curator` | dataset inspection, validation, and metadata |
| `render` | `fasthep-render` | plotting, reports, and rendering utilities |
| `cli` | `fasthep-cli` | unified command-line interface |
| `toolbench` | `fasthep-toolbench` | shared utilities and user-facing helpers |
| `workshop` | `fasthep-workshop` | examples, tutorials, and training material |
| `main-docs` | `fast-hep.github.io` | main FAST-HEP documentation site |

Use canonical names when discussing packages and repositories. Use local names when referring to workspace paths.

## Common commands

```bash
git submodule status --recursive
git submodule update --remote --recursive
```

Once Pixi tooling is configured:

```bash
pixi install
pixi run --environment scripts repo-index
pixi run --environment dev smoke-imports
pixi run --environment dev ci
```

## Purpose

`fasthep-dev` is intended for:

* cross-package development
* integration testing
* release validation
* shared tooling
* AI/developer navigation indexes
* documentation coordination

Package-specific development still happens inside the individual package repositories.

## Notes

Generated indexes and local build artifacts should not be committed unless explicitly intended.

## Release procedure

FAST-HEP releases are coordinated from this development workspace.

Release versions are defined in `releases.json`

`workshop` and `fasthep` are pinned-last: their dependency pins get rewritten to exact versions
(`==`), and an exact pin can only ever resolve against a package that already has a real git tag —
an editable, not-yet-tagged dependency always reports a dev-snapshot version instead. So their
pins are updated, and they're tagged, strictly after everything they depend on already has a real
tag — never together with the rest, and never before. `scripts/release/update_versions.py` refuses
to write an exact pin to an untagged dependency (`release_data.validate_pin_readiness`), so getting
the order below wrong fails loudly rather than leaving an unresolvable `pixi.toml`/`pyproject.toml`.

1. Review the plan: `pixi run release-plan` (validates topological release order; a failure here
   means `releases.json` itself needs fixing before anything else).
2. Check repo state: `pixi run release-check` (validates calendar-versioned version numbers and
   `workshop/pixi.toml` pins, in addition to order).
3. Tag every package except `workshop` and `fasthep`: `pixi run release-tag-dry` then
   `pixi run release-tag` then `pixi run release-tag-push`. (Their own "version" update is a no-op
   for every package here — all are dynamically versioned via `hatch-vcs` — so there is nothing to
   update before tagging them; skip straight to tagging.)
4. Update `workshop`'s version and pins, now that everything it depends on is tagged:
   `pixi run release-update-versions-workshop-dry` then `pixi run release-update-versions-workshop`
   (rewrites `workshop/pyproject.toml` and `workshop/pixi.toml`'s FAST-HEP pins to `==`).
5. Re-run `pixi run release-check` and confirm it passes.
6. Tag and push `workshop`: `pixi run release-tag-workshop-dry` then `pixi run release-tag-workshop`
   then `pixi run release-tag-workshop-push`.
7. **Stop.** Run workshop's tutorials/examples locally (`cd workshop && pixi run test-smoke`, or the
   equivalent full tutorial run) and confirm they're green — this is a manual step, not CI, per the
   workshop AGENTS.md tutorial-execution policy.
8. Once workshop's tag is pushed and its CI/Read the Docs build is green, aggregate the changelog:
   `pixi run release-aggregate-changelog-dry` then `pixi run release-aggregate-changelog`, and
   commit the resulting `fasthep/CHANGELOG.md`.
9. Update `fasthep`'s pins, now that `workshop` is tagged too:
   `pixi run release-update-versions-fasthep-dry` then `pixi run release-update-versions-fasthep`.
10. Tag and push the meta package last: `pixi run release-tag-fasthep-dry` then
    `pixi run release-tag-fasthep` then `pixi run release-tag-fasthep-push`.

If `pixi run` fails to solve an environment partway through for an unrelated reason (for example
the AFS lock on lxplus), fall back to the environment's own Python directly, e.g.
`.pixi/envs/scripts/bin/python scripts/release/tag_packages.py releases.json --package workshop`.

During alpha, normal PyPI-based CI may be marked as non-blocking. The temporary alpha CI workflows install FAST-HEP dependencies from Git and should be treated as the relevant integration signal.
