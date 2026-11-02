#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. Groups and
# the judged events are in events.json, the one home merge/merge.py reads too. A red run is cleared when
# the newest completed run of another group of the same workflow is newer, succeeded, and ran every job
# the red run ran, each with conclusion success (clears.py, the one home of that rule; the jobs come
# from `gh run view`, read only for a red run). Env: BRANCH, SELF (this workflow's name, left out),
# GH_TOKEN, GITHUB_REPOSITORY. Exit 0 always: the alarm is the issue, not a red job. Prints "green",
# "red" or "unknown"; a failed or empty read, of runs, jobs or the issue write, is unknown, never red.
set -o pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
unknown() { echo unknown; echo "::warning::ci-alarm: $1"; exit 0; }
runs="$(gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" --status completed \
  --limit 100 --json workflowName,workflowDatabaseId,databaseId,conclusion,createdAt,url,event)" \
  || unknown "gh run list failed"
jq -e 'type == "array"' >/dev/null 2>&1 <<<"$runs" || unknown "gh run list gave no list of runs"
# Only workflow files under .github/workflows count, whatever their state but "deleted" (a disabled one
# still has a file, and merge.py judges it): a deleted workflow keeps its last run for ever, and a Pages
# build has no file. A run whose workflow is not in the list is not judged.
wf="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows" --paginate)" || unknown "gh api workflows failed"
flows="$(jq -e -s 'if length > 0 and all(.[]; (.workflows | type) == "array") then [.[].workflows[]] else empty end' <<<"$wf" 2>/dev/null)" \
  || unknown "gh api workflows gave no list of workflows"
# Latest completed run per workflow and event group, each with its group.
latest="$(jq -c --arg self "${SELF:-}" --slurpfile ev "$here/events.json" --argjson flows "$flows" '
  ([$flows[] | select(.state != "deleted" and (.path | startswith(".github/workflows/"))) | .id]) as $ids
  | map(select(.workflowName != $self and (.workflowDatabaseId as $i | $ids | index($i)) and ($ev[0][.event] != null))
        | . + {group: $ev[0][.event]})
  | group_by([.workflowDatabaseId, .group])
  | map(sort_by(.createdAt) | last)' <<<"$runs")" || unknown "could not read the runs"
# The jobs of run $1 as a JSON list in run_jobs. Not a subshell, so unknown can end the script.
jobs_of() {
  local out
  out="$(gh run view "$1" --repo "$GITHUB_REPOSITORY" --json jobs)" || unknown "gh run view $1 failed"
  run_jobs="$(jq -ce '.jobs | select(type == "array")' <<<"$out" 2>/dev/null)" && [ -n "$run_jobs" ] \
    || unknown "gh run view $1 gave no list of jobs"
}
# Red = failure, timed_out or startup_failure. A red run stands unless a newer successful run of another
# group of its workflow passed all its jobs (clears.py). Jobs are read only when such a newer run exists.
red=""
while IFS= read -r r; do
  newer="$(jq -r --argjson r "$r" '.[] | select(.workflowDatabaseId == $r.workflowDatabaseId and .group != $r.group
    and .createdAt > $r.createdAt and .conclusion == "success") | .databaseId' <<<"$latest")" || unknown "could not read the runs"
  cleared=no
  if [ -n "$newer" ]; then
    jobs_of "$(jq -r .databaseId <<<"$r")"; red_jobs="$run_jobs"
    for id in $newer; do
      jobs_of "$id"
      verdict="$(python3 "$here/clears.py" "$red_jobs" "$run_jobs")" || unknown "clears.py failed"
      if [ "$verdict" = yes ]; then cleared=yes; break; fi
    done
  fi
  if [ "$cleared" = no ]; then
    red="${red:+$red$'\n'}$(jq -r '"- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$r")"
  fi
done < <(jq -c '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure")' <<<"$latest")
if [ -z "$red" ]; then echo green; exit 0; fi
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
