# FAST-HEP layout guide

If you are changing...

## Workflow engine

- author.yaml parsing/lowering → `fasthep-flow`
- workflow IR/plans → `fasthep-flow`
- runtime orchestration/backends → `fasthep-flow`
- registries/spec loading → `fasthep-flow`
- dependency inference → `fasthep-flow`

## Analysis/runtime components

- ROOT reading/writing → `fasthep-carpenter`
- awkward-array transforms → `fasthep-carpenter`
- histogram filling → `fasthep-carpenter`
- cutflows → `fasthep-carpenter`
- experiment-specific transforms → `fasthep-carpenter`

## Metadata/diagnostics

- schema snapshots/errors/warnings → `fasthep-curator`
- provenance/environment capture → `fasthep-curator`
- validation hooks → `fasthep-curator`
- dataset inspection → `fasthep-curator`

## Rendering/output

- plots/render styles → `fasthep-render`
- report generation → `fasthep-render`
- render sinks → `fasthep-render`

## CLI/user interaction

- CLI commands → `fasthep-cli`
- console formatting/display helpers → `fasthep-toolbench`
- package discovery/version display → `fasthep-toolbench`
- downloads/helpers → `fasthep-toolbench`

## Examples/tutorials

- workshop examples/tutorials → `fasthep-workshop`
- downloadable training datasets → `fasthep-workshop`

## Integration/release coordination

- submodule orchestration → `fasthep-dev`
- integration smoke tests → `fasthep-dev`
- release validation → `fasthep-dev`

## Planned future packages

- statistical tooling/datacards → `fasthep-stats`
- validation/comparison workflows → `fasthep-validate`
- GitLab/CERN CI integrations → `fasthep-gitlab`