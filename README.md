Replace it with:
# fasthep-dev

Development and integration workspace for the FAST-HEP ecosystem.

This repository is **not** an installable Python package. It collects the FAST-HEP repositories as Git submodules and provides shared tooling for development, testing, and release validation.

## Clone

This workspace uses SSH Git submodule URLs by default.

```bash
git clone --recurse-submodules git@github.com:FAST-HEP/fasthep-dev.git
cd fasthep-dev
````

If submodules are missing:

```bash
git submodule update --init --recursive
```

## Packages

This workspace includes:

* `fasthep`

  * meta package and verified compatibility bundle
* `fasthep-flow`

  * workflow compilation, planning, and orchestration
* `fasthep-carpenter`

  * HEP analysis transforms and histogramming
* `fasthep-curator`

  * dataset inspection, validation, and metadata
* `fasthep-render`

  * plotting, reports, and rendering utilities
* `fasthep-cli`

  * unified command-line interface
* `fasthep-toolbench`

  * shared utilities and user-facing helpers
* `fasthep-workshop`

  * examples, tutorials, and training material
* `fast-hep.github.io`

  * main FAST-HEP documentation site

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
