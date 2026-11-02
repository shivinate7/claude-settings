#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. Groups and
# the judged events are in events.json, the one home merge/merge.py reads too. A red run is cleared when
# the newest completed run of another group of the same workflow is newer, succeeded, and ran every job
# the red run ran, each with conclusion success (clears.py, the one home of that rule: it picks the
# candidate runs and judges the job sets; the jobs come from `gh api --paginate`, read only for a red run
# that has a candidate). Env: BRANCH, SELF (this workflow's name, left out), GH_TOKEN, GITHUB_REPOSITORY.
# Exit 0 always: the alarm is the issue, not a red job. Prints "green", "red" or "unknown". A failed or
# empty read of the runs, the workflows or the issue write is unknown, never red. A failed jobs read makes
# only that red run unknown: a red run elsewhere still prints red, then unknown, then green (as merge.py).
set -o pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
tmp="$(mktemp -d)" || { echo unknown; echo "::warning::ci-alarm: mktemp failed"; exit 0; }
trap 'rm -rf "$tmp"' EXIT
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
# The judged runs, in the shape clears.py reads (id, wf, event, status, conclusion, created_at), each with its group.
jq -c --arg self "${SELF:-}" --slurpfile ev "$here/events.json" --argjson flows "$flows" '
  ([$flows[] | select(.state != "deleted" and (.path | startswith(".github/workflows/"))) | .id]) as $ids
  | map(select(.workflowName != $self and (.workflowDatabaseId as $i | $ids | index($i)) and ($ev[0][.event] != null))
        | {id: .databaseId, wf: .workflowDatabaseId, event, status: "completed", conclusion, created_at: .createdAt,
           name: .workflowName, url, group: $ev[0][.event]})' <<<"$runs" > "$tmp/runs.json" || unknown "could not read the runs"
# The newest run of each workflow and event group.
latest="$(jq -c 'group_by([.wf, .group]) | map(sort_by(.created_at) | last)' "$tmp/runs.json")" || unknown "could not read the runs"
# Read the jobs of run $1 into the file $2 as a JSON list, every page merged. On failure, why holds the cause.
# Not a subshell, so the caller can read why.
read_jobs() {
  local out
  out="$(gh api --paginate "repos/$GITHUB_REPOSITORY/actions/runs/$1/jobs")" || { why="gh api jobs of run $1 failed"; return 1; }
  jq -e -s 'if length > 0 and all(.[]; (.jobs | type) == "array") then [.[].jobs[]] else empty end' <<<"$out" > "$2" 2>/dev/null \
    || { why="gh api jobs of run $1 gave no list of jobs"; return 1; }
}
# Red = failure, timed_out or startup_failure. A red run stands unless a candidate (clears.py) passed all its jobs.
red=""
unk=""
while IFS= read -r r; do
  id="$(jq -r .id <<<"$r")"
  cands="$(python3 "$here/clears.py" candidates "$tmp/runs.json" "$here/events.json" "$id")" || unknown "clears.py failed"
  cleared=no
  failed=""
  if [ -n "$cands" ]; then
    if read_jobs "$id" "$tmp/red.json"; then
      for n in $cands; do
        if ! read_jobs "$n" "$tmp/newer.json"; then failed="$why"; continue; fi
        verdict="$(python3 "$here/clears.py" clears "$tmp/red.json" "$tmp/newer.json")" || unknown "clears.py failed"
        if [ "$verdict" = yes ]; then cleared=yes; break; fi
      done
    else
      failed="$why"
    fi
  fi
  if [ "$cleared" = yes ]; then continue; fi
  if [ -n "$failed" ]; then
    unk="${unk:+$unk$'\n'}$failed"
  else
    red="${red:+$red$'\n'}$(jq -r '"- \(.name) (\(.conclusion)): \(.url)"' <<<"$r")"
  fi
done < <(jq -c '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure")' <<<"$latest")
if [ -z "$red" ]; then
  if [ -n "$unk" ]; then unknown "$(tr '\n' ';' <<<"$unk")"; fi
  echo green; exit 0
fi
if [ -n "$unk" ]; then echo "::warning::ci-alarm: left unjudged: $(tr '\n' ';' <<<"$unk")"; fi
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
