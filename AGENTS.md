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

## Workspace repository names

The development workspace intentionally uses short local directory names.

| Local path | Canonical repository/package |
|---|---|
| `flow` | `fasthep-flow` |
| `carpenter` | `fasthep-carpenter` |
| `render` | `fasthep-render` |
| `curator` | `fasthep-curator` |
| `cli` | `fasthep-cli` |
| `toolbench` | `fasthep-toolbench` |
| `workshop` | `fasthep-workshop` |
| `main-docs` | `fast-hep.github.io` |
| `fasthep` | meta package |
| `legacy-hepflow` | legacy reference copy |

Use canonical names when discussing packages and repositories.
Use local names when referring to workspace paths.

## Package boundaries

- `fasthep-flow` / import `hepflow`
  - workflow compiler, plans, runtime orchestration, registries, backends, public API

- `fasthep-carpenter` / import `fasthep_carpenter`
  - HEP analysis transforms, ROOT/awkward sources and writers, histogram filling, cutflows

- `fasthep-curator` / import `fasthep_curator`
  - metadata, schemas, inspection, diagnostics, provenance

- `fasthep-render` / import `fasthep_render`
  - rendering sinks, plots, reports, styles

- `fasthep-cli` / import `fasthep_cli`
  - `fasthep` command-line interface; should remain a thin wrapper over public APIs
  - If a CLI command needs more than a small adapter function, the implementation probably belongs outside `fasthep-cli`.

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

### CLI implementation boundary

`fasthep-cli` must remain a thin command-line wrapper over public APIs provided by the owning packages.

Do not implement workflow, compiler, runtime, registry, profile, or project-initialisation logic directly in `fasthep-cli`.

CLI commands should generally:

1. parse command-line options
2. call a public API from the owning package
3. format/display the result
4. return an appropriate exit code

For example:

- `fasthep init` should delegate to `hepflow.api.init_project`
- workflow compilation should delegate to `hepflow.api`
- runtime execution should delegate to the owning flow/runtime API
- package discovery or utility helpers should live in `fasthep-toolbench` where appropriate

If a CLI change requires new behaviour, first add or update the public API in the owning package, then call that API from `fasthep-cli`.

Avoid adding business logic to CLI modules beyond argument parsing, validation, and presentation.

## Public API discipline

Public API modules should stay small, readable, and discoverable.

For `hepflow.api`, the intended pattern is:

- public orchestration functions live in `hepflow.api`
- implementation details live in owning modules
- `api.py` delegates to compiler, runtime, registry, profile, backend, or product modules

Good:

```python
def make_plan_file(...):
    return make_plan_from_normalized_file(...)
```

Bad:

```python
def make_plan_file(...):
    ...
    # large implementation
```

Private helpers in `api.py` should be rare.

Before adding a private helper to `api.py`, ask:

1. Does this belong in an existing module?
2. Does this feature need a new focused module?
3. Would another public function reuse this implementation?

If a feature needs more than one private helper, move the implementation out of `api.py` and keep `api.py` as a thin facade.

As a rule of thumb, private helpers whose names contain domain concepts such as `plan`, `compile`, `systematics`, `registry`, `runtime`, `product`, or `render` probably do not belong in `api.py`.

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
```

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
```

## Test placement

Tests for `src/hepflow/<subsystem>/...` should normally live under
`tests/<subsystem>/...`.

Tests that intentionally span multiple subsystems may remain at the test root.

Do not force one test file per source file; group by subsystem and behaviour.

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

## fasthep-workshop conventions
User-facing documentation must assume:

1. git clone fasthep-workshop
2. cd fasthep-workshop
3. pixi install

Do not assume:
- FAST-HEP development workspace
- sibling repositories
- editable installs
- local package checkouts

Developer instructions belong in contributor documentation, not tutorials.

- Repository root is the canonical working directory.
- All documentation, tutorials, examples, and READMEs must assume commands are executed from the repository root unless explicitly stated otherwise.
- Do not assume the FAST-HEP development meta-repository layout.
- Do not prepend "workshop/" or other parent-directory prefixes when referring to files inside this repository.
- Paths in documentation, tutorials, examples, tests, and READMEs should be relative to the repository root.

Correct:
    tutorials/01-read-data/root-files/workflow.yaml

Incorrect:
    workshop/tutorials/01-read-data/root-files/workflow.yaml

## Prefer established upstream functionality

Before implementing numerical, histogram, plotting, vector, particle-data, or
array-manipulation helpers, check whether the functionality already exists in
the project’s upstream libraries.

Prefer, in roughly this order:

1. An existing FAST-HEP abstraction.
2. A public API from an existing dependency.
3. A well-maintained Scikit-HEP package.
4. A small local implementation only when no suitable upstream API exists.

Do not copy helpers from legacy analysis repositories without first checking
the upstream-library index in:

`docs/upstream-libraries.md`

When using upstream functionality:

- use public APIs rather than internal attributes
- preserve the upstream object abstraction
- avoid converting to NumPy merely to reimplement an available operation
- add a focused test demonstrating the expected upstream behaviour
- document why a local implementation is needed when upstream functionality
  was considered and rejected


## Keep workflows concise

Author YAML should describe analysis intent, not repeat information that can be
derived by the operation spec.

Before adding parameters to an author-facing operation, ask whether they can be
derived from existing parameters through `requires`, `provides`, defaults, or
normalisation.

Prefer:

```yaml
params:
  collection: Muon
  output: selected_loose_Muon
  selection:
    - pt >= 5
    - abs(eta) <= 2.4
  keep:
    - pt
    - eta
    - phi
```

over:

```yaml
params:
  input_fields:
    - Muon_pt
    - Muon_eta
    - Muon_phi
  output_fields:
    - selected_loose_Muon_pt
    - selected_loose_Muon_eta
    - selected_loose_Muon_phi
```

Operation specs should derive:

* required fields from collection references, expressions, retained fields,
  sorting fields, and other operation parameters
* provided fields from output prefixes, retained fields, and naming conventions
* default values for common cases
* generated count or diagnostic fields where their names are deterministic

Use the existing spec mechanisms before extending core Flow syntax or adding
redundant author parameters.

Good author-facing parameters describe concepts such as:

* collection
* output
* selection
* keep
* variations
* resource
* sort

Avoid exposing:

* fully expanded required branch lists
* fully expanded output field lists
* duplicate prefixes and derived names
* runtime-only implementation details
* parameters that repeat information already available elsewhere in the same
  operation

The normalised plan and compiled graph should remain explicit and inspectable,
even when workflow YAML is compact.

When reviewing a new operation, treat excessive author verbosity as an API
design issue, not merely a documentation issue.


### New operation review checklist

- Can `requires` be derived from params?
- Can `provides` be derived from params?
- Are output names deterministic?
- Is the user repeating collection prefixes?
- Is configuration describing intent or implementation?
- Can defaults remove common boilerplate?
- Does the compiled representation remain explicit?
