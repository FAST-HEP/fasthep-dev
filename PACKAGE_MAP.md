# FAST-HEP layout guide

## Workspace repositories

| Workspace path | Repository | Python package | Distribution |
|---|---|---|---|
| `flow` | `fasthep-flow` | `hepflow` | `fasthep-flow` |
| `carpenter` | `fasthep-carpenter` | `fasthep_carpenter` | `fasthep-carpenter` |
| `curator` | `fasthep-curator` | `fasthep_curator` | `fasthep-curator` |
| `render` | `fasthep-render` | `fasthep_render` | `fasthep-render` |
| `cli` | `fasthep-cli` | `fasthep_cli` | `fasthep-cli` |
| `toolbench` | `fasthep-toolbench` | `fasthep_toolbench` | `fasthep-toolbench` |
| `workshop` | `fasthep-workshop` | `fasthep_workshop` | `fasthep-workshop` |
| `main-docs` | `fast-hep.github.io` | n/a | n/a |
| `fasthep` | `fasthep` | `fasthep` | `fasthep` |
| `legacy-hepflow` | legacy hepflow reference | `hepflow` | n/a |

Use workspace paths for local filesystem references and canonical names for packages, repositories, imports, and distributions.

If you are changing...

## Workflow engine

- workflow.yaml parsing/lowering → `fasthep-flow` in `flow/`
- workflow IR/plans → `fasthep-flow` in `flow/`
- runtime orchestration/backends → `fasthep-flow` in `flow/`
- registries/spec loading → `fasthep-flow` in `flow/`
- dependency inference → `fasthep-flow` in `flow/`

## Analysis/runtime components

- ROOT reading/writing → `fasthep-carpenter` in `carpenter/`
- awkward-array transforms → `fasthep-carpenter` in `carpenter/`
- histogram filling → `fasthep-carpenter` in `carpenter/`
- cutflows → `fasthep-carpenter` in `carpenter/`
- experiment-specific transforms → `fasthep-carpenter` in `carpenter/`

## Metadata/diagnostics

- schema snapshots/errors/warnings → `fasthep-curator` in `curator/`
- provenance/environment capture → `fasthep-curator` in `curator/`
- validation hooks → `fasthep-curator` in `curator/`
- dataset inspection → `fasthep-curator` in `curator/`

## Rendering/output

- plots/render styles → `fasthep-render` in `render/`
- report generation → `fasthep-render` in `render/`
- render sinks → `fasthep-render` in `render/`

## CLI/user interaction

- CLI commands → `fasthep-cli` in `cli/`
- console formatting/display helpers → `fasthep-toolbench` in `toolbench/`
- package discovery/version display → `fasthep-toolbench` in `toolbench/`
- downloads/helpers → `fasthep-toolbench` in `toolbench/`

## Examples/tutorials

- workshop examples/tutorials → `fasthep-workshop` in `workshop/`
- downloadable training datasets → `fasthep-workshop` in `workshop/`

## Integration/release coordination

- submodule orchestration → `fasthep-dev`
- integration smoke tests → `fasthep-dev`
- release validation → `fasthep-dev`

## Planned future packages

- statistical tooling/datacards → `fasthep-stats`
- validation/comparison workflows → `fasthep-validate`
- GitLab/CERN CI integrations → `fasthep-gitlab`
