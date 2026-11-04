#!/usr/bin/env bash
# Runs the wiring rules over the calling workflow. WORKFLOW is a path relative to GITHUB_WORKSPACE.
# Exit codes of the rules script pass through: 0 clean, 1 a problem, 2 unknown. Only a 0 from it is a pass.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${WORKFLOW:-}" ]; then
  echo "all-jobs-passed: no workflow input, wiring check skipped"
  exit 0
fi
out="$(python3 "$here/../../lint/all_jobs_passed_rules.py" --workflow "$GITHUB_WORKSPACE/$WORKFLOW" 2>&1)"; rc=$?
printf '%s\n' "$out"
case "$rc" in
  0) exit 0 ;;
  1) exit 1 ;;
  2) echo "::error title=all-jobs-passed::The wiring is unknown: $WORKFLOW could not be read (the caller job may lack a checkout)."
     exit 2 ;;
  *) exit "$rc" ;;
esac
