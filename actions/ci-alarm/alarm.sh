#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. Groups and
# the judged events are in events.json, the one home merge/merge.py reads too. Env: BRANCH, SELF
# (this workflow's name, left out), GH_TOKEN, GITHUB_REPOSITORY. Exit 0 always: the alarm is the
# issue, not a red job. Prints "green", "red" or "unknown"; a failed read or write is unknown, never red.
set -o pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
unknown() { echo unknown; echo "::warning::ci-alarm: $1"; exit 0; }
runs="$(gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" --status completed \
  --limit 100 --json workflowName,workflowDatabaseId,conclusion,createdAt,url,event)" \
  || unknown "gh run list failed"
# Only active workflows that are files under .github/workflows count: a deleted workflow keeps
# its last run for ever, and a Pages build has no file.
flows="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows" --paginate | jq -s '[.[].workflows[]]')" \
  || unknown "gh api workflows failed"
# Latest completed run per workflow and event group; red = failure, timed_out or startup_failure.
red="$(jq -r --arg self "${SELF:-}" --slurpfile ev "$here/events.json" --argjson flows "$flows" '
  ([$flows[] | select(.state == "active" and (.path | startswith(".github/workflows/"))) | .id]) as $ids
  | map(select(.workflowName != $self and (.workflowDatabaseId as $i | $ids | index($i)) and ($ev[0][.event] != null))
        | . + {group: $ev[0][.event]})
  | group_by([.workflowDatabaseId, .group])
  | map(sort_by(.createdAt) | last)
  | map(select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure"))
  | .[] | "- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$runs")" \
  || unknown "could not read the runs"
if [ -z "$red" ]; then echo green; exit 0; fi
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
