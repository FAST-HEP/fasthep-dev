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
| `legacy-hepflow` | legacy hepflow reference | historical reference copy |

Use canonical names when discussing packages and repositories. Use local names when referring to workspace paths.

## Common commands

```bash
git submodule status --recursive
git submodule update --remote --recursive
```

Once Pixi tooling is configured:

```bash
pixi install
pixi run --environment tools repo-index
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
