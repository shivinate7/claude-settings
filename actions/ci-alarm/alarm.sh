#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. Groups and
# the judged events are in events.json, the one home merge/merge.py reads too. A failed run R with a
# red job (conclusion neither success, skipped, neutral nor cancelled) is cleared by a run N of the same
# workflow and another group only when all of these hold: N is newer than R, is the newest of its group
# and succeeded; N's head sha equals R's, or GitHub's compare of R's sha...N's sha reads ahead or
# identical (one read, only when the shas differ; a missing sha on either side clears nothing); and every
# job name of R that has an entry neither success nor skipped is a job of N, exact match, each of its
# entries success. A job of R that passed or was skipped needs no entry in N. An R with no red job (no
# jobs, all passed, cancelled or skipped only) is never cleared this way. A cancelled run never alarms.
# The jobs of R and N are read only for a failed group that has such an N (one read each); a failed jobs
# or compare read is unknown. The same failed-run rule as Host.base_state. Env: BRANCH, SELF
# (this workflow's name, left out), GH_TOKEN, GITHUB_REPOSITORY. Exit 0 always: the alarm is the
# issue, not a red job. Prints "green", "red" or "unknown"; a failed read or write is unknown, never red.
set -o pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
unknown() { echo unknown; echo "::warning::ci-alarm: $1"; exit 0; }
runs="$(gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" --status completed \
  --limit 100 --json workflowName,workflowDatabaseId,databaseId,conclusion,createdAt,url,event,headSha)" \
  || unknown "gh run list failed"
jq -e 'type == "array"' >/dev/null 2>&1 <<<"$runs" || unknown "gh run list gave no list of runs"
# Only workflow files under .github/workflows count, whatever their state but "deleted" (a disabled one
# still has a file, and merge.py judges it): a deleted workflow keeps its last run for ever, and a Pages
# build has no file. A run whose workflow is not in the list is not judged.
wf="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows" --paginate)" || unknown "gh api workflows failed"
flows="$(jq -e -s 'if length > 0 and all(.[]; (.workflows | type) == "array") then [.[].workflows[]] else empty end' <<<"$wf" 2>/dev/null)" \
  || unknown "gh api workflows gave no list of workflows"
# Latest completed run per workflow and event group, one JSON array.
newest="$(jq -c --arg self "${SELF:-}" --slurpfile ev "$here/events.json" --argjson flows "$flows" '
  ([$flows[] | select(.state != "deleted" and (.path | startswith(".github/workflows/"))) | .id]) as $ids
  | map(select(.workflowName != $self and (.workflowDatabaseId as $i | $ids | index($i)) and ($ev[0][.event] != null))
        | . + {group: $ev[0][.event]})
  | group_by([.workflowDatabaseId, .group])
  | map(sort_by(.createdAt) | last)' <<<"$runs")" \
  || unknown "could not read the runs"
# The jobs of one run, as a JSON array; a failed read returns 1. Each run is read once.
cache="$(mktemp -d)" || unknown "could not make a temp dir"
trap 'rm -rf "$cache"' EXIT
jobs_of() {
  if [ ! -f "$cache/$1" ]; then
    local raw
    raw="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$1/jobs?per_page=100" --paginate)" || return 1
    jq -e -s 'if length > 0 and all(.[]; (.jobs | type) == "array") then [.[].jobs[]] else empty end' <<<"$raw" > "$cache/$1" 2>/dev/null \
      || { rm -f "$cache/$1"; return 1; }
  fi
  cat "$cache/$1"
}
# Red = failure, timed_out or startup_failure, unless a clearing run N exists (see the header).
red=""
failed="$(jq -c '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure")' <<<"$newest")" \
  || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  cands="$(jq -c --argjson r "$r" '.[] | select(.workflowDatabaseId == $r.workflowDatabaseId and .group != $r.group
    and .createdAt > $r.createdAt and .conclusion == "success" and .headSha != null and $r.headSha != null) | {id: .databaseId, sha: .headSha}' <<<"$newest")" \
    || unknown "could not read the runs"
  if [ -n "$cands" ]; then
    rjobs="$(jobs_of "$(jq -r .databaseId <<<"$r")")" || unknown "gh api jobs failed"
    if jq -e 'any(.[]; .status == "completed" and (.conclusion | IN("success", "skipped", "neutral", "cancelled") | not))' >/dev/null <<<"$rjobs"; then
      rsha="$(jq -r .headSha <<<"$r")"
      while IFS= read -r cand; do
        n="$(jq -r .id <<<"$cand")"; nsha="$(jq -r .sha <<<"$cand")"
        njobs="$(jobs_of "$n")" || unknown "gh api jobs failed"
        # the cover set: each job name of R with an entry neither success nor skipped must be in N, each entry success
        jq -e --argjson n "$njobs" '[.[] | select(.conclusion | IN("success", "skipped") | not) | .name] | unique | all(. as $x | ($n | map(select(.name == $x))) as $m
            | ($m | length) > 0 and all($m[]; .conclusion == "success"))' >/dev/null <<<"$rjobs" || continue
        [ "$rsha" = "$nsha" ] && continue 2
        st="$(gh api "repos/$GITHUB_REPOSITORY/compare/$rsha...$nsha" --jq .status)" || unknown "gh api compare failed"
        case "$st" in ahead|identical) continue 2 ;; esac
      done <<<"$cands"
    fi
  fi
  red+="$(jq -r '"- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$r")"$'\n'
done <<<"$failed"
red="${red%$'\n'}"
if [ -z "$red" ]; then echo green; exit 0; fi
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
