#!/usr/bin/env bash
# Alarm when the latest completed run of any workflow on BRANCH is red. Env: BRANCH, SELF
# (this workflow's name, left out), GH_TOKEN, GITHUB_REPOSITORY. Exit 0 either way: the alarm
# is the issue, not a red job. Prints "red" or "green".
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
runs="$(gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" --status completed \
  --limit 100 --json workflowName,conclusion,createdAt,url)"
# Latest completed run per workflow; red = failure, timed_out or startup_failure.
red="$(jq -r --arg self "${SELF:-}" '
  map(select(.workflowName != $self)) | group_by(.workflowName)
  | map(sort_by(.createdAt) | last)
  | map(select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure"))
  | .[] | "- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$runs")"
if [ -z "$red" ]; then echo green; exit 0; fi
echo red
bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")"
