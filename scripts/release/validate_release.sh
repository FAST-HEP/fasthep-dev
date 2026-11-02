#!/usr/bin/env bash
# Validate a FAST-HEP release by running workshop's examples and tutorials 01 to 06 in workshop's
# own (released) pixi environment. This is the manual step after tagging workshop: the runs use the
# packages published on PyPI, not this workspace's editable ones.
#
# Dry run by default: prints what it would run and which input files are missing. Nothing is
# executed or written without --run.
#
#   scripts/release/validate_release.sh                    # dry run, latest workshop tag
#   scripts/release/validate_release.sh --run              # run everything
#   scripts/release/validate_release.sh --run --version 2026.11.1 --skip 02-transform-data/03-field-mapping
set -uo pipefail

RUN=0
VERSION=""
WORKSHOP="workshop"
SKIP=("01-read-data/03-remote-data")   # remote data: needs network or credentials
# Local inputs the examples and tutorials read, relative to the workshop directory. The developer
# populates them (some need credentials) from the remote_data.json / files.json manifests.
REQUIRED_DATA=(
  data/CMS/Zmumu/data.root
  data/CMS/L1Trigger/2k.root
  data/CMS/L1Trigger/2kmu.root
  data/LZ/mssi/SS_skim_Th232-late_HVInnerCone.root
)
EXAMPLES=("CMS/Zmumu:CMS-Zmumu" "CMS/L1Trigger:CMS-L1Trigger" "LZ/mssi:LZ-mssi")

while (($#)); do
  case "$1" in
    --run) RUN=1 ;;
    --version) VERSION="${2:?--version needs a value}"; shift ;;
    --workshop) WORKSHOP="${2:?--workshop needs a directory}"; shift ;;
    --skip) SKIP+=("${2:?--skip needs a tutorial path}"); shift ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -z "$VERSION" ]]; then
  VERSION="$(git -C "$WORKSHOP" tag --sort=-v:refname | head -n 1)"
  [[ -n "$VERSION" ]] || { echo "no tag in $WORKSHOP and no --version given" >&2; exit 2; }
fi
echo "Validating release $VERSION (workshop: $WORKSHOP, $([[ $RUN == 1 ]] && echo run || echo dry run))"

head_tag="$(git -C "$WORKSHOP" describe --tags --exact-match 2>/dev/null || true)"
if [[ "$head_tag" != "$VERSION" ]]; then
  echo "warning: workshop HEAD is not at tag $VERSION (${head_tag:-no tag}); the examples and tutorials" \
       "come from the working tree" >&2
fi

missing=0
for f in "${REQUIRED_DATA[@]}"; do
  if [[ ! -e "$WORKSHOP/$f" ]]; then
    echo "MISSING: $WORKSHOP/$f (populate from the example's remote_data.json or tutorials/data/*/files.json)"
    missing=1
  fi
done
if ((missing && RUN)); then
  echo "stopping: required input files are missing" >&2
  exit 2
fi

is_skipped() { local s; for s in "${SKIP[@]}"; do [[ "$1" == "$s" ]] && return 0; done; return 1; }

LOGDIR="$WORKSHOP/build/$VERSION-validation"
SUMMARY="$LOGDIR/summary.txt"
if ((RUN)); then mkdir -p "$LOGDIR"; : > "$SUMMARY"; fi
failed=0

run_one() {   # name workflow outdir
  local name="$1" workflow="$2" outdir="$3"
  local cmd=(pixi run fasthep run "$workflow" "--outdir=$outdir")
  if ((! RUN)); then
    echo "[dry-run] (cd $WORKSHOP && ${cmd[*]})"
    return
  fi
  echo "running $name ..."
  (cd "$WORKSHOP" && "${cmd[@]}") > "$LOGDIR/$name.log" 2>&1
  local rc=$?
  echo "$rc $name" >> "$SUMMARY"
  ((rc == 0)) || { failed=$((failed + 1)); echo "  FAILED (exit $rc), log: $LOGDIR/$name.log"; }
}

for entry in "${EXAMPLES[@]}"; do
  path="${entry%%:*}"; label="${entry##*:}"
  run_one "example-$label" "examples/$path/workflow.yaml" "build/$VERSION-$label"
done

for wf in "$WORKSHOP"/tutorials/0[1-6]-*/*/workflow.yaml; do
  [[ -e "$wf" ]] || continue
  tutorial="${wf#"$WORKSHOP"/tutorials/}"; tutorial="${tutorial%/workflow.yaml}"
  if is_skipped "$tutorial"; then echo "skipping $tutorial"; continue; fi
  label="${tutorial//\//-}"
  run_one "tutorial-$label" "tutorials/$tutorial/workflow.yaml" "build/$VERSION-tutorial-$label"
done

if ((RUN)); then
  echo
  cat "$SUMMARY"
  echo "summary: $SUMMARY (build/ is not kept: copy it into reports/ if it matters)"
  ((failed == 0)) && echo "all runs passed" || echo "$failed run(s) failed"
  exit $((failed > 0))
fi
