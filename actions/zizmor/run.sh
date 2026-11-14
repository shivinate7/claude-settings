#!/usr/bin/env bash
# The one home of the pinned zizmor run: the action calls it, and bin/ci-job --lint runs it in place.
# ZIZMOR_PATHS holds the paths to audit, separated by spaces or newlines; unset means .github/. Empty fails closed,
# because a run with no path to audit must not read as a pass. Exit code is pipx's own.
set -u
paths="${ZIZMOR_PATHS-.github/}"
# -d '' reads the whole value, so a `paths: |` block's newlines split like spaces. No glob expansion, no eval.
read -r -d '' -a targets <<< "$paths"
if [ "${#targets[@]}" -eq 0 ]; then
  echo "run.sh: ZIZMOR_PATHS is empty, so there is nothing to audit" >&2
  exit 2
fi
exec pipx run zizmor==1.32.0 "${targets[@]}"
