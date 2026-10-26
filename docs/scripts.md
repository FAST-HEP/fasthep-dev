# Workspace Script Catalogue

Use these scripts from the `fasthep-dev` repository root. Do not run mutating,
release, submission, or external-write scripts merely to inspect them.

| Script | Purpose | Typical invocation | Environment | External services or credentials | Effect |
|---|---|---|---|---|---|
| `scripts/dev/git-status-summary.py` | Summarise dirty state and upstream sync for local submodule checkouts. | `pixi run --environment scripts git-status` or `python scripts/dev/git-status-summary.py` | `scripts` Pixi env or system Python with Git available | Git remotes only if upstream comparison needs configured remotes; no credentials for local status | Read-only |
| `scripts/dev/repo_index.py` | Generate compact package, symbol, profile, command, test, and registry indexes. | `pixi run --environment scripts repo-index` or `python scripts/dev/repo_index.py --out .ai` | `scripts` Pixi env; optional PyYAML improves YAML parsing | None | Mutating: writes index files, default `.ai/` |
| `scripts/dev/clean_build.py` | List `build/` run directories below the workspace (FAST-HEP only, `hinv/` is skipped) and, on request, delete selected ones. Protects folders that contain, or sit below, a `clean.keep` file, and folders with git-tracked files. | List: `pixi run --environment scripts clean-build`; delete: `pixi run --environment scripts clean-build-execute --older-than 14` (or `--all`, `--only GLOB`, `--whole`) | `scripts` Pixi env or system Python with Git | None | Read-only by default; destructive with `--execute`: needs a selection and a typed confirmation on a terminal, refuses without one, no option to skip (human gate) |
| `scripts/dev/push_branches.py` | Show, and on request push, the FAST-HEP branches of a stacked PR set listed in `tasks/push-manifest.yaml`; never forces, skips diverged branches. | Dry run: `pixi run --environment scripts push-branches`; push: `pixi run --environment scripts push-branches-execute` | `scripts` Pixi env or system Python with Git and PyYAML | Git remotes (SSH keys); `ls-remote` in the dry run | Read-only external query by default; external-write with `--execute`: typed confirmation on a terminal, refuses without one, no option to skip (human gate) |
| `scripts/dev/tasks_sync.py` | Mirror open issues of the FAST-HEP roadmap project (GitHub) into `tasks/issues/`. | `pixi run --environment scripts tasks-sync` (dry run: `tasks-sync-dry`) | `scripts` Pixi env or system Python | `GITHUB_TOKEN` from the environment or from the env file given with `--env-file` or `FASTHEP_ENV_FILE` (location differs per machine; read only, never printed) | Read-only towards GitHub; writes local files below `tasks/issues/` (only files it generated); `--prune` deletes stale generated files and is a human gate |
| `scripts/helpers/condor_info.py` | Print basic HTCondor collector and scheduler information. | `python scripts/helpers/condor_info.py` | Python with `htcondor2` installed and HTCondor client configured | HTCondor collector/schedd access; site configuration may require credentials | Read-only external query |
| `scripts/release/check_release.py` | Check release readiness from `releases.json`: clean repos, branches, package metadata, and existing tags. | `pixi run --environment scripts release-check` or `python scripts/release/check_release.py releases.json` | `scripts` Pixi env or Python with stdlib TOML support | Git remotes for remote tag checks; network/auth may be needed for private remotes | Read-only but can contact remotes |
| `scripts/release/print_release_plan.py` | Print release order, versions, distributions, tags, and manual hard stops. | `pixi run --environment scripts release-plan` or `python scripts/release/print_release_plan.py releases.json` | `scripts` Pixi env or system Python | None | Read-only |
| `scripts/release/update_versions.py` | Update package versions and FAST-HEP dependency pins from `releases.json`. `workshop` and `fasthep` (`release_data.PINNED_LAST`) are only updated via `--package`, and a non-dry-run refuses (`release_data.validate_pin_readiness`) if any FAST-HEP dependency it would pin isn't tagged yet. | Default batch (all packages except `workshop`/`fasthep`) dry run: `pixi run --environment scripts release-update-versions-dry`; write: `pixi run --environment scripts release-update-versions`. `workshop` only: `release-update-versions-workshop-dry` / `release-update-versions-workshop`. `fasthep` only: `release-update-versions-fasthep-dry` / `release-update-versions-fasthep` | `scripts` Pixi env; needs `packaging` | None | Mutating unless `--dry-run` |
| `scripts/release/tag_packages.py` | Create and optionally push annotated release tags in package repositories. A batch run with no `--package` always excludes `workshop` and `fasthep` (`release_data.PINNED_LAST`); tag each individually, after its pins are updated, once everything it depends on is already tagged. | Default batch dry run: `pixi run --environment scripts release-tag-dry`; create local tags: `release-tag`; push: `release-tag-push`. `workshop` only: `release-tag-workshop-dry` / `release-tag-workshop` / `release-tag-workshop-push`. `fasthep` only: `release-tag-fasthep-dry` / `release-tag-fasthep` / `release-tag-fasthep-push` | `scripts` Pixi env or system Python with Git | Git remotes and push credentials when `--push` is used | Mutating; potentially external-write with `--push` |
| `scripts/release/tests/test_tag_packages.py` | Unit tests for release tag naming/message helpers. | `pixi run --environment dev pytest scripts/release/tests/test_tag_packages.py` | `dev` Pixi env or Python with pytest | None | Read-only test |
| `scripts/release/tests/test_update_versions.py` | Unit tests for dependency pin rewriting and dry-run behaviour. | `pixi run --environment dev pytest scripts/release/tests/test_update_versions.py` | `dev` Pixi env or Python with pytest and `packaging` | None | Read-only test using temporary files |

Notes:

- `pixi.toml` exposes release helpers as tasks in the `scripts` environment.
- `clean` removes `__pycache__`, caches and `dist/` only; `build/` folders are handled by
  `clean-build` (they are gitignored and can hold the only copy of validation outputs).
- `pixi run` can fail on the AFS lock on lxplus; the scripts also run directly with the
  environment's Python, for example `hinv/.pixi/envs/dev/bin/python scripts/dev/clean_build.py`.
- `release-tag-push` writes to Git remotes; use only when explicitly requested.
- Destructive or external-write actions (`clean-build-execute`, `push-branches-execute`, `--prune`) are
  human gates: a typed confirmation on a terminal, refused without one, no flag to skip it. Agents do
  not run them.
- `hinv/` (CMS analysis integration) is not FAST-HEP: its tooling lives in `hinv/chip` and the
  workspace scripts and pixi tasks do not touch it.
- `scripts/helpers/condor_info.py` is intentionally live-site dependent and
  should not be part of routine local documentation checks.
