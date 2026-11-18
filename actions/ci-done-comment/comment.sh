#!/usr/bin/env bash
# Posts a PR comment for a red run. With JOB set (a failing job's own last step), it names that
# job at once, so the watcher wakes while other jobs run. Without JOB (the run-end job), it names
# each job that ended failure or cancelled and was not already announced for this run attempt.
# Prints the body and posts nothing when CI_DONE_DRY=1 (the test seam; ANNOUNCED is then a
# space-separated job list). A green run prints nothing and posts nothing. A skipped job is not
# red: the scope job skips jobs a change does not need. A failed post warns and exits 0, because
# a red job here wakes no one either.
set -euo pipefail
post() { # $1 = body
  if [ "${CI_DONE_DRY:-}" = 1 ]; then printf '%s\n' "$1"; return 0; fi
  gh pr comment "$PR" --repo "$REPO" --body "$1" || echo "::warning::CI done comment not posted on PR $PR"
}
if [ -n "${JOB:-}" ]; then
  post "<!-- ci-done -->
<!-- ci-job:${JOB} -->
CI job ${JOB} failed on ${SHA:0:7}. Other jobs run on.
Run: ${RUN_URL}"
  exit 0
fi
announced="${ANNOUNCED:-}"
if [ "${CI_DONE_DRY:-}" != 1 ]; then
  # One read per run: the comments this run attempt already posted name their jobs in a marker.
  announced="$(gh api --paginate "repos/${REPO}/issues/${PR}/comments" \
    --jq ".[] | select(.body | contains(\"${RUN_URL}\")) | .body | capture(\"<!-- ci-job:(?<j>[^ ]+) -->\").j" 2>/dev/null | tr '\n' ' ' || true)"
fi
red="$(echo "$NEEDS" | jq -r --arg a "$announced" '($a | split(" ")) as $done
  | [to_entries[] | select(.value.result == "failure" or .value.result == "cancelled")
  | select(.key as $k | $done | index($k) | not) | "\(.key) (\(.value.result))"] | join(", ")')"
[ -n "$red" ] || { echo "No red job: no comment."; exit 0; }
post "<!-- ci-done -->
CI finished red on ${SHA:0:7}: ${red}.
Run: ${RUN_URL}"
