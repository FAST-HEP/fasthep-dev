# Workspace Layout

The workspace uses short local directory names while preserving canonical package and repository names.

| Local path | Canonical repository/package |
|---|---|
| `flow` | `fasthep-flow` |
| `carpenter` | `fasthep-carpenter` |
| `curator` | `fasthep-curator` |
| `render` | `fasthep-render` |
| `cli` | `fasthep-cli` |
| `toolbench` | `fasthep-toolbench` |
| `workshop` | `fasthep-workshop` |
| `main-docs` | `fast-hep.github.io` |
| `fasthep` | meta package |
| `legacy-hepflow` | legacy reference copy |

If you are changing...

- author.yaml parsing/lowering → `fasthep-flow` in `flow/`
- required data inference → `fasthep-flow` in `flow/` plus component spec in the owning package
- ROOT reading/writing → `fasthep-carpenter` in `carpenter/`
- schema snapshots/errors/warnings → `fasthep-curator` in `curator/`
- plots/render styles → `fasthep-render` in `render/`
- CLI commands → `fasthep-cli` in `cli/`
- examples/tutorials → `fasthep-workshop` in `workshop/`
