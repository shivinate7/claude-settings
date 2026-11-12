#!/usr/bin/env bash
# Alarm when the newest completed run of any (workflow, event group) on BRANCH is red. Groups and
# the judged events are in events.json, the one home merge/merge.py reads too. A failed run R with a
# red job (conclusion neither success, skipped, neutral nor cancelled) is cleared by a run N of the same
# workflow and another group only when N is newer than R, is the newest of its group, succeeded, and
# passes what R needs (clear_rule.py, the one home of the rule, which merge.py calls too): every job name of R, exact match, has
# conclusion success in every N entry, except a job of R that is not red in R and whose job-level `if:` has a top-level `&&` conjunct
# `github.event_name == 'X'` with X not N's event (all-jobs-passed and ci-done run on pull_request only, so a push or schedule run
# skips them). So a newer green push run clears a red nightly. An R with no red job (no jobs,
# all passed, cancelled or skipped only) is never cleared this way. Cost, only for a failed group that has
# such an N: one jobs read for R, and for each N one jobs read and, unless N leaves a red job of R unpassed (a certain red), one contents read of N's workflow file at N's head (headSha), each once;
# a failed read is unknown. The same failed-run rule as Host.base_state. Needs python3 (stdlib only) and
# clear_rule.py beside this file; no checkout.
# A cancelled run is red only when one of its jobs was cancelled at its own job-level `timeout-minutes`: the job ran at least that
# long (completed_at - started_at, from the jobs read), the cap read from the run's workflow file at its head. The alarm names the
# job, the cap and the run id. A job cancelled under its cap (a person, or an earlier failure) stays quiet. A cancelled job with
# no started_at, no integer cap, or no single job of that name in the file, a run with no jobs, or a failed read is unknown,
# never red and never clear. Cost per cancelled run judged (the newest of its group): one jobs read, and one contents read
# only when a job of it was cancelled; the cap is read with awk, so no interpreter starts. Env: BRANCH, SELF
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
# Red = failure, timed_out or startup_failure (and, further down, a cancelled run with a job cancelled at its cap), unless a clearing run N exists (see the header).
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
  red+="$(jq -r '"- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$r")"$'\n'
done <<<"$failed"
# The job-level timeout-minutes of the job named $2 in workflow file $1: an integer above 0, from the one job whose key or `name:` is
# that name (a matrix suffix ` (...)` is dropped when no job has the full name). Prints nothing and returns 1 when no single job
# matches or its cap is no such integer. A job-level key is a line at the indent of the first line under the job key, so a
# `timeout-minutes` in a step, a run block or a comment is not read.
CAP_AWK="$(cat <<'AWK'
function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
function value(s,   q, rest, i) {
  s = trim(s); q = substr(s, 1, 1)
  if (q == "\"" || q == "'") { rest = substr(s, 2); i = index(rest, q); return i ? substr(rest, 1, i - 1) : s }
  sub(/[ \t]+#.*$/, "", s)
  if (s ~ /^#/) s = ""
  return trim(s)
}
function indent(s) { match(s, /^ */); return RLENGTH }
{ sub(/\r$/, "") }
/^[ \t]*(#.*)?$/ { next }
/^jobs:[ \t]*(#.*)?$/ { injobs = 1; ji = -1; cur = 0; next }
/^[^ \t]/ { injobs = 0; next }
!injobs { next }
{
  n = indent($0); line = trim($0)
  if (ji < 0) ji = n
  if (n == ji) {
    cur = 0
    if (line ~ /^[^:]+:[ \t]*(#.*)?$/) { cur = ++jobs; k = line; sub(/:.*$/, "", k); key[cur] = value(k); ki = -1 }
  } else if (cur && n > ji) {
    if (ki < 0) ki = n
    if (n == ki && line ~ /^name:/) name[cur] = value(substr(line, 6))
    if (n == ki && line ~ /^timeout-minutes:/) cap[cur] = value(substr(line, 17))
  }
}
END {
  w2 = want; sub(/[ \t]+\(.*\)$/, "", w2); c = 0
  for (i = 1; i <= jobs; i++) if (key[i] == want || name[i] == want) { c++; hit = i }
  if (c == 0 && w2 != want) for (i = 1; i <= jobs; i++) if (key[i] == w2 || name[i] == w2) { c++; hit = i }
  if (c != 1 || cap[hit] !~ /^[0-9]+$/ || cap[hit] + 0 < 1) exit 1
  print cap[hit] + 0
}
AWK
)"
cap_of() { awk -v want="$2" "$CAP_AWK" "$1"; }
# Cancelled runs: red when a job of the run was cancelled at its cap (see the header). An unknown waits until the end, so a red
# found here or above still opens its issue.
capunk=""
cancelled="$(jq -c '.[] | select(.conclusion == "cancelled")' <<<"$newest")" || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  rid="$(jq -r .databaseId <<<"$r")"
  rjobs="$(jobs_of "$rid")" || { capunk="gh api jobs failed for run $rid"; continue; }
  if jq -e 'length == 0' >/dev/null <<<"$rjobs"; then capunk="cancelled run $rid has no jobs"; continue; fi
  # Seconds each cancelled job ran, or "never" (no started_at or completed_at, or a time that does not parse), then its name.
  lines="$(jq -r '.[] | select(.status == "completed" and .conclusion == "cancelled")
    | (try ((.completed_at | fromdateiso8601) - (.started_at | fromdateiso8601)) catch null) as $s
    | "\(if $s == null or $s < 0 then "never" else ($s | floor) end)\t\(.name)"' <<<"$rjobs")" || { capunk="could not read the jobs of run $rid"; continue; }
  [ -n "$lines" ] || continue
  workflow_of "$rid" || { capunk="gh api contents failed for run $rid"; continue; }
  while IFS=$'\t' read -r secs name; do
    if [ "$secs" = never ]; then capunk="job $name of run $rid has no readable start and end time"; continue; fi
    cap="$(cap_of "$cache/wf-$rid" "$name")" || { capunk="job $name of run $rid has no single job-level timeout-minutes in its workflow file"; continue; }
    [ "$secs" -ge $((cap * 60)) ] || continue
    red+="$(jq -r --arg job "$name" --arg cap "$cap" --arg mins "$((secs / 60))" \
      '"- \(.workflowName) (cancelled at its cap): job \($job) ran \($mins) min, cap \($cap) min, run \(.databaseId): \(.url)"' <<<"$r")"$'\n'
  done <<<"$lines"
done <<<"$cancelled"
red="${red%$'\n'}"
if [ -z "$red" ] && [ -n "$capunk" ]; then unknown "$capunk"; fi
if [ -z "$red" ]; then echo green; exit 0; fi
# issue.sh prints nothing on success and `unknown` plus a warning when the issue write fails.
res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'Latest run is red on %s:\n\n%s' "$branch" "$red")")"
if grep -qx unknown <<<"$res"; then echo "$res"; else echo red; fi
