#!/usr/bin/env bash
# The action's one step. Runs both checks every time, so a failed needs check never hides a wiring defect
# and the reverse. Exits non-zero when either check does. NEEDS and WORKFLOW come from the step's env.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
needs_rc=0
wiring_rc=0
bash "$here/check.sh" || needs_rc=$?
bash "$here/wiring.sh" || wiring_rc=$?
if [ "$needs_rc" -ne 0 ]; then exit "$needs_rc"; fi
exit "$wiring_rc"
