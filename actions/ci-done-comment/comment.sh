#!/usr/bin/env bash
# Posts one PR comment naming the jobs that ended failure or cancelled. Prints the body and posts
# nothing when CI_DONE_DRY=1 (the test seam). A green run prints nothing and posts nothing. A skipped
# job is not red: the scope job skips jobs a change does not need. A failed post warns and exits 0,
# because a red job here wakes no one either.
set -euo pipefail
red="$(echo "$NEEDS" | jq -r '[to_entries[] | select(.value.result == "failure" or .value.result == "cancelled")
  | "\(.key) (\(.value.result))"] | join(", ")')"
[ -n "$red" ] || { echo "No red job: no comment."; exit 0; }
body="<!-- ci-done -->
CI finished red on ${SHA:0:7}: ${red}.
Run: ${RUN_URL}"
if [ "${CI_DONE_DRY:-}" = 1 ]; then printf '%s\n' "$body"; exit 0; fi
gh pr comment "$PR" --repo "$REPO" --body "$body" || echo "::warning::CI done comment not posted on PR $PR"
