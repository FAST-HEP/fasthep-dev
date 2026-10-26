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

1. Review the plan: `pixi run release-plan` (now also validates topological order and calendar
   versions; a failure here means `releases.json` itself needs fixing before anything else).
2. Check repo state: `pixi run release-check` (now also validates `workshop/pixi.toml` pins).
3. Update versions and pins: `pixi run release-update-versions-dry` then `pixi run release-update-versions`
   (now also rewrites `workshop/pixi.toml`'s FAST-HEP pins to `==`).
4. Re-run `pixi run release-check` and confirm it passes.
5. Tag every package except `fasthep`: `pixi run release-tag` then `pixi run release-tag-push`.
6. **Stop before tagging `workshop`'s dependents further and before `fasthep`.** Run workshop's
   tutorials/examples locally (`pixi run -e workshop test-smoke` or the equivalent full tutorial
   run) and confirm they're green — this is a manual step, not CI, per the workshop AGENTS.md
   tutorial-execution policy.
7. Once workshop's tag is pushed and its CI/Read the Docs build is green, aggregate the changelog:
   `pixi run release-aggregate-changelog-dry` then `pixi run release-aggregate-changelog`, and
   commit the resulting `fasthep/CHANGELOG.md`.
8. Tag the meta package last:
   `python scripts/release/tag_packages.py releases.json --package fasthep --push`.

During alpha, normal PyPI-based CI may be marked as non-blocking. The temporary alpha CI workflows install FAST-HEP dependencies from Git and should be treated as the relevant integration signal.
