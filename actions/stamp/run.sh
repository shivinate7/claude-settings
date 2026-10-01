#!/usr/bin/env bash
# The composite action's own logic, pulled out of action.yml so it can be run and tested
# directly (test_action.sh does exactly that) rather than only inside a GitHub Actions runner.
#
# MODE is "check", the only mode. It runs `stamp.mjs --check`. It needs only STAMP_JS and CONFIG.
# No default branch, no gate, no commit, no push, so it runs with `contents: read` on any branch
# or pull request. BASE is optional. When set, it passes through as `--base`. When empty, it is
# left out. Any other MODE, including the removed "stamp", is refused.
set -euo pipefail

MODE="${MODE:-check}"

case "$MODE" in
  check)
    # BASE, when set, names the base. Else the engine picks it: origin/$GITHUB_BASE_REF on a pull
    # request, else origin/<defaultBranch>. Its exit code is this run's verdict.
    exec node "$STAMP_JS" --check ${BASE:+--base "$BASE"} --config "$CONFIG"
    ;;
  *)
    echo "stamp REFUSES: mode is '$MODE'. The only mode is 'check'. Mode 'stamp' was removed: claim the number at merge with merge/merge.py."
    exit 2
    ;;
esac
