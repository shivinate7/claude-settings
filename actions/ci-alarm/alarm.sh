#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. The verdict is
# clear_rule.py `judge`, the one home of the selection (which runs decide, what clears a red run, what
# makes a job red), which merge/merge.py calls too; this file fetches and prints. Groups and the judged
# events are in events.json. A run is red on conclusion failure, timed_out or startup_failure; a cancelled run never
# alarms. A red run is cleared only by a newer green run of another group (clear_rule.py, with its cost: jobs reads
# of the runs it compares and one read of the workflow file at the clearing run's head). A re-run in flight is unknown,
# never green: the older run under it is the one being re-run. Needs python3 (stdlib only), gh and clear_rule.py beside
# this file; no checkout. Env: BRANCH, SELF (this workflow's name, left out), GH_TOKEN, GITHUB_REPOSITORY. Exit 0
# always: the alarm is the issue, not a red job. Prints "green", "red" or "unknown"; a failed read or write is
# unknown, never red.
set -o pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
unknown() { echo unknown; echo "::warning::ci-alarm: $1"; exit 0; }
# In-flight runs are fetched too (no --status): the judge needs a re-run in flight above an older run.
runs="$(gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" \
  --limit 100 --json workflowName,workflowDatabaseId,databaseId,conclusion,createdAt,url,event,headSha,status,attempt)" \
  || unknown "gh run list failed"
jq -e 'type == "array"' >/dev/null 2>&1 <<<"$runs" || unknown "gh run list gave no list of runs"
# Only workflow files under .github/workflows count, whatever their state but "deleted": clear_rule.py reads this list.
wf="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows" --paginate)" || unknown "gh api workflows failed"
flows="$(jq -e -s 'if length > 0 and all(.[]; (.workflows | type) == "array") then [.[].workflows[]] else empty end' <<<"$wf" 2>/dev/null)" \
  || unknown "gh api workflows gave no list of workflows"
cache="$(mktemp -d)" || unknown "could not make a temp dir"
trap 'rm -rf "$cache"' EXIT
printf '%s' "$runs" > "$cache/runs"
printf '%s' "$flows" > "$cache/flows"
res="$(python3 "$here/clear_rule.py" --judge "$cache/runs" --flows "$cache/flows" --repo "$GITHUB_REPOSITORY" --self "${SELF:-}")" \
  || unknown "clear_rule.py failed"
verdict="${res%%$'\n'*}"
detail="${res#"$verdict"}"
detail="${detail#$'\n'}"
case "$verdict" in
  green) echo green; exit 0 ;;
  unknown) unknown "$detail" ;;
  red) ;;
  *) unknown "clear_rule.py gave no verdict" ;;
esac
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$detail")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
