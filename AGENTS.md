Use this as a first version:

````md
# FAST-HEP agent instructions

This repository is the `fasthep-dev` integration workspace.

It is not an installable Python package. It collects FAST-HEP repositories as Git submodules and provides shared tooling, smoke tests, release validation, and navigation aids.

## Start here

Before editing code:

1. Read `PACKAGE_MAP.md`.
2. Read `docs/layout.md`.
3. Identify the owning package.
4. Make changes in the owning submodule, not in unrelated packages.
5. Prefer small, focused changes.

Do not scan the whole workspace unless necessary.

## Package boundaries

- `fasthep-flow` / import `hepflow`
  - workflow compiler, plans, runtime orchestration, registries, backends, public API

- `fasthep-carpenter` / import `fasthep_carpenter`
  - HEP analysis transforms, ROOT/awkward sources and writers, histogram filling, cutflows

- `fasthep-curator` / import `fasthep_curator`
  - metadata, schemas, inspection, diagnostics, hooks, provenance

- `fasthep-render` / import `fasthep_render`
  - rendering sinks, plots, reports, styles

- `fasthep-cli` / import `fasthep_cli`
  - `fasthep` command-line interface; should remain a thin wrapper over public APIs

- `fasthep-toolbench` / import `fasthep_toolbench`
  - shared display, download, package discovery, and lightweight UX helpers

- `fasthep-workshop`
  - examples, tutorials, training material, download manifests

- `fasthep`
  - meta package and compatibility bundle only; no implementation logic

- `fast-hep.github.io`
  - main documentation site

- `fasthep-dev`
  - integration workspace, submodule orchestration, release validation, shared tooling

## Dependency rules

`fasthep-flow` must remain lightweight and must not depend on:

- `fasthep-carpenter`
- `fasthep-curator`
- `fasthep-render`
- ROOT/uproot-specific logic
- plotting/rendering libraries
- experiment-specific code

Extension packages contribute functionality through registry/profile layers.

The CLI should call public APIs and helper packages. It should not import compiler/runtime internals directly.

## Editing rules

- Keep changes local to the owning package where possible.
- Add or update tests in the same package as the change.
- Avoid broad rewrites unless explicitly requested.
- Do not edit generated files such as `_version.py`.
- Do not commit caches, build products, or large generated artifacts.
- Do not modify legacy/reference directories unless explicitly asked.

## Package-local vs workspace checks

Package repositories should keep release-like dependency declarations.

Do not replace package dependencies with `../local-path` editable dependencies in package-local `pixi.toml` files unless explicitly requested.

For cross-package editable testing, use the `fasthep-dev` workspace instead:

```bash
pixi run --environment dev test-cli
pixi run --environment dev smoke-imports
pixi run --environment dev ci
```
when validating a package as an independently releasable project.

## Common commands

Lightweight workspace tools:

```bash
pixi run --environment tools repo-index
git submodule status --recursive
````

Full editable ecosystem checks:

```bash
pixi run --environment dev smoke-imports
pixi run --environment dev ci
```

Submodule maintenance:

```bash
git submodule update --init --recursive
git submodule update --remote --recursive
```

## Workspace integration checks

The `fasthep-dev` workspace installs FAST-HEP packages from local submodules as editable packages.

Use workspace tasks when validating cross-package changes:

```bash
pixi run --environment dev smoke-imports
pixi run --environment dev test-flow
pixi run --environment dev test-cli
pixi run --environment dev lint-all
pixi run --environment dev typecheck-all
pixi run --environment dev ci

## AI contribution expectations

AI-assisted changes are welcome, but they must be reviewable.

For non-trivial changes, include in the final summary:

* what was changed
* why it was changed
* which package owns the change
* tests/checks run
* any design assumptions
* any follow-up TODOs

Humans remain responsible for submitted code. Generated code that cannot be explained should not be submitted.

## When unsure

Use this routing rule:

* workflow semantics → `fasthep-flow`
* HEP transforms / ROOT / awkward / hist filling → `fasthep-carpenter`
* metadata / schemas / diagnostics / provenance → `fasthep-curator`
* plots / reports / visual output → `fasthep-render`
* user commands → `fasthep-cli`
* generic display/download helpers → `fasthep-toolbench`
* examples/templates → `fasthep-workshop`
* cross-package integration → `fasthep-dev`
