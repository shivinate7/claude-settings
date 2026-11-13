#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. Groups and
# the judged events are in events.json, the one home merge/merge.py reads too. A failed run R with a
# red job (conclusion neither success, skipped, neutral nor cancelled) is cleared by a run N of the same
# workflow and another group only when N is newer than R, is the newest of its group, succeeded, and
# passes what R needs (clear_rule.py, the one home of the rule, which merge.py calls too): every job name of R, exact match, has
# conclusion success in every N entry, except a job of R that is not red in R and whose job-level `if:` has a top-level `&&` conjunct
# `github.event_name == 'X'` with X not N's event (all-jobs-passed and ci-done run on pull_request only, so a push or schedule run
# skips them). So a newer green push run clears a red nightly. An R with no red job (no jobs,
# all passed, cancelled or skipped only) is never cleared this way. A cancelled run never alarms. Cost, only for a failed group that has
# such an N: one jobs read for R, and for each N one jobs read and, unless N leaves a red job of R unpassed (a certain red), one contents read of N's workflow file at N's head (headSha), each once;
# a failed read is unknown. The same failed-run rule as Host.base_state.
# A failed run that nothing clears is also lifted by a live revert on BRANCH (revert_rule.py, the one home of the rule, which merge.py
# reads too; the same rule as Host.base_state's revert clear): a commit reachable from BRANCH, other than the run's headSha, with
# `This reverts commit <headSha>` (40 hex) in its message, not net-reverted (an odd chain is a revert). Each red run needs its own
# revert. It never clears a cancelled run (never alarms anyway), a re-run in flight (not listed: --status completed) or a failed read (unknown).
# Cost, per failed run with no clearing run: one search/commits read, and one compare read per revert link; none when every run is green.
# Commit search sees the default branch only, so a BRANCH that is not the default finds no revert: it alarms and never clears.
# Needs python3 (stdlib only) and clear_rule.py and revert_rule.py beside this file; no checkout. Env: BRANCH, SELF
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
# The workflow file at the head of run $1, in $cache/wf-$1 (one read per run); a failed read returns 1.
workflow_of() {
  [ -f "$cache/wf-$1" ] && return 0
  local run path sha
  run="$(jq -c --argjson n "$1" '.[] | select(.databaseId == $n)' <<<"$newest")" || return 1
  path="$(jq -r --argjson i "$(jq .workflowDatabaseId <<<"$run")" '.[] | select(.id == $i) | .path' <<<"$flows")" || return 1
  sha="$(jq -r '.headSha // empty' <<<"$run")"
  { [ -n "$path" ] && [ -n "$sha" ]; } || return 1
  gh api "repos/$GITHUB_REPOSITORY/contents/$path?ref=$sha" -H "Accept: application/vnd.github.raw+json" > "$cache/wf-$1" || { rm -f "$cache/wf-$1"; return 1; }
  [ -s "$cache/wf-$1" ] || { rm -f "$cache/wf-$1"; return 1; }
}
# True (0) when a live revert on the branch lifts the failed run with head sha $1 (revert_rule.py); a failed read is unknown. One read set per head.
reverted() {
  [ -n "$1" ] || return 1
  if [ ! -f "$cache/rev-$1" ]; then
    python3 "$here/revert_rule.py" --repo "$GITHUB_REPOSITORY" --branch "$branch" --head "$1"
    echo $? > "$cache/rev-$1"
  fi
  case "$(cat "$cache/rev-$1")" in 0) return 0 ;; 1) return 1 ;; *) unknown "revert_rule.py could not read the reverts" ;; esac
}
# Red = failure, timed_out or startup_failure, unless a clearing run N exists or a live revert lifts it (see the header).
red=""
failed="$(jq -c '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure")' <<<"$newest")" \
  || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  cands="$(jq -r --argjson r "$r" '.[] | select(.workflowDatabaseId == $r.workflowDatabaseId and .group != $r.group
    and .createdAt > $r.createdAt and .conclusion == "success") | .databaseId' <<<"$newest")" || unknown "could not read the runs"
  if [ -n "$cands" ]; then
    rid="$(jq -r .databaseId <<<"$r")"
    rjobs="$(jobs_of "$rid")" || unknown "gh api jobs failed"
    if jq -e 'any(.[]; .status == "completed" and (.conclusion | IN("success", "skipped", "neutral", "cancelled") | not))' >/dev/null <<<"$rjobs"; then
      while IFS= read -r n; do
        jobs_of "$n" >/dev/null || unknown "gh api jobs failed"
        # Step one reads no workflow: a red job of R that N lacks or did not pass is a certain red, so N clears nothing.
        python3 "$here/clear_rule.py" --red-stays "$cache/$rid" "$cache/$n"
        case $? in 0) continue ;; 1) ;; *) unknown "clear_rule.py failed" ;; esac
        workflow_of "$n" || unknown "gh api contents failed"
        python3 "$here/clear_rule.py" --event "$(jq -r --argjson n "$n" '.[] | select(.databaseId == $n) | .event' <<<"$newest")" \
          --workflow "$cache/wf-$n" "$cache/$rid" "$cache/$n"
        case $? in 0) continue 2 ;; 1) ;; *) unknown "clear_rule.py failed" ;; esac
      done <<<"$cands"
    fi
  fi
  reverted "$(jq -r '.headSha // empty' <<<"$r")" && continue
  red+="$(jq -r '"- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$r")"$'\n'
done <<<"$failed"
red="${red%$'\n'}"
if [ -z "$red" ]; then echo green; exit 0; fi
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
