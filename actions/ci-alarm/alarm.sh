#!/usr/bin/env bash
# Alarm when the newest run of any (workflow, event group) on BRANCH is red, or when any run in the 100-run window holds a job cancelled
# at its time cap. Groups and the judged events are in events.json, the one home merge/merge.py reads too.
# Red: a failed run R with a red job (conclusion neither success, skipped, neutral nor cancelled) is cleared by a run N of the same
# workflow and another group only when N is newer than R, is the newest of its group, succeeded, and passes what R needs (clear_rule.py,
# the one home of the rule, which merge.py calls too). Every job name of R, exact match, must have conclusion success in every N entry,
# except a job of R that is not red in R and whose job-level `if:` has a top-level `&&` conjunct `github.event_name == 'X'` with X not
# N's event (all-jobs-passed and ci-done run on pull_request only, so a push or schedule run skips them). So a newer green push run
# clears a red nightly. An R with no red job (no jobs, all passed, cancelled or skipped only) is never cleared this way. Same failed-run
# rule as Host.base_state.
# A group whose newest run is a re-run still going (queued or in progress, attempt above 1) is unknown: a warning, no issue, never
# green, never the older run. A first attempt still going is skipped, and the older run is judged.
# An empty green run of the push group (no check ran, no evidence: clear_rule.py) is no verdict; the group's newest counting run that is
# not empty is, so an older red run stays red. A group with only empty runs keeps its newest run. The same rule as Host.base_state.
# Cap end (owner, page item 549 a, 12:07 CST Nov 12; judged in every run of the window, coordinator pick 12:26 CST): a job cancelled
# at its cap ran at least its job-level `timeout-minutes` (completed_at - started_at, from the jobs read), the cap read from the run's
# workflow file at its head. A job with no job-level `timeout-minutes` has GitHub's default cap, 360 minutes. Every such job is named
# and its run is woken, wherever it sits:
#   - in any cancelled run of the window, newest of its group or not, and in each earlier attempt of it;
#   - in any earlier attempt of a succeeded re-run;
#   - in any failed run of the window, newest of its group or not, in its newest attempt or an earlier one, whether a newer green run
#     clears the run or not.
# The clear drops a run's red jobs, never its cap end. The merge gate (merge.py base_state) leaves a run with no red job and a job timed
# out at a job-level cap it finds in its checkout out of red and out of unknown; a cancelled run reads UNKNOWN there for a job with no
# job-level cap or a cap it does not find, and a failure run reads red. The alarm is the signal, since a cap end is not a red job.
# A job cancelled under its cap (a person, or an earlier failure) stays quiet. A cancelled job with no started_at, a non-integer cap
# (an expression), no single job of that name in the file, a cancelled run or an earlier attempt of it with no jobs, or a failed read
# is unknown, never red and never clear.
# Verdict: "red" when a newest failure run, not cleared, is named. That run opens the issue "CI red on BRANCH" through
# issue.sh. The issue names the red runs and no cap end: a cap end wakes and never appears in an issue. Else "alarm" (a cap end and no
# red run), which opens no issue (owner R53, 13:07 CST Nov 12).
# Each attempt with a cap end, in either verdict, is woken through wake.sh (coordinator pick, 13:12 CST): SHA is the run's head commit,
# KEY is `cap:<run id>:<attempt>`, and TEXT opens with "CI job hit its time cap on BRANCH: JOB", the first cap job of that attempt, then
# names the cap ends of that attempt. wake.sh posts on the merged pull request into main that holds the commit, once per KEY (its hidden
# marker is the memory), so a cap end already reported is not reported again (coordinator ruling, 12:58 CST), while a cap end in a later
# attempt of the same run still wakes. A run whose commit has no such pull request cannot be woken: wake.sh exits non-zero, and after
# every attempt was handled this script prints its verdict and exits 1, naming the run id and attempt.
# A failed read or write is unknown, never red. A failed jobs read of a newest red run drops its cap end with no warning, and a failed read of
# a cancelled run is a soft unknown that a red verdict hides (debt note cap-jobs-read-drops-silent).
# Cost per alarm: two fixed reads (runs, workflows list), one jobs read for each failed and each cancelled run of the 100-run window (at
# most 100), one per earlier attempt of a failed, cancelled or succeeded re-run, one contents read of a run's workflow file when a job of
# it was cancelled. A clear candidate N adds one jobs read, and one contents read of N's workflow file at N's head (headSha) unless N
# leaves a red job of R unpassed (a certain red), and two clear_rule.py starts at most. Each green run of the push group, newest first, down
# to the first that is not empty, adds one jobs read (the empty-run test). Each woken attempt adds one pulls read, one
# comments read of its pull request (one per 100 comments) and at most one comment write (wake.sh). No long-lived process starts: short jq (unmeasured),
# awk (unmeasured), gh and python3 processes run. The files written are temp cache files in a folder this script removes on exit, and a failed wake
# appends one message to GITHUB_STEP_SUMMARY.
# Needs python3 (stdlib only) and clear_rule.py beside this file; no checkout.
# Env: BRANCH, SELF (this workflow's name, left out), GH_TOKEN, GITHUB_REPOSITORY. Exit 0, except 1 when a cap end could not be woken.
set -o pipefail
here="$(cd "$(dirname "$0")" && pwd)"
branch="${BRANCH:-main}"
unknown() { echo unknown; echo "::warning::ci-alarm: $1"; exit 0; }
runs="$(gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" \
  --limit 100 --json workflowName,workflowDatabaseId,databaseId,conclusion,status,createdAt,url,event,headSha,attempt)" \
  || unknown "gh run list failed"
jq -e 'type == "array"' >/dev/null 2>&1 <<<"$runs" || unknown "gh run list gave no list of runs"
# Only workflow files under .github/workflows count, whatever their state but "deleted" (a disabled one
# still has a file, and merge.py judges it): a deleted workflow keeps its last run for ever, and a Pages
# build has no file. A run whose workflow is not in the list is not judged.
wf="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows" --paginate)" || unknown "gh api workflows failed"
flows="$(jq -e -s 'if length > 0 and all(.[]; (.workflows | type) == "array") then [.[].workflows[]] else empty end' <<<"$wf" 2>/dev/null)" \
  || unknown "gh api workflows gave no list of workflows"
# Every run of a judged workflow and event group, with its group. The cancelled and re-run loops below judge each of them.
judged="$(jq -c --arg self "${SELF:-}" --slurpfile ev "$here/events.json" --argjson flows "$flows" '
  ([$flows[] | select(.state != "deleted" and (.path | startswith(".github/workflows/"))) | .id]) as $ids
  | map(select(.workflowName != $self and (.workflowDatabaseId as $i | $ids | index($i)) and ($ev[0][.event] != null))
        | . + {group: $ev[0][.event]})' <<<"$runs")" \
  || unknown "could not read the runs"
cache="$(mktemp -d)" || unknown "could not make a temp dir"
trap 'rm -rf "$cache"' EXIT
# The jobs of run $1 (of its attempt $2 when given, else its newest attempt), as a JSON array; a failed read returns 1. Each is read once.
jobs_of() {
  local key="$1${2:+.a$2}" route="repos/$GITHUB_REPOSITORY/actions/runs/$1${2:+/attempts/$2}/jobs?per_page=100" raw
  if [ ! -f "$cache/$key" ]; then
    raw="$(gh api "$route" --paginate)" || return 1
    jq -e -s 'if length > 0 and all(.[]; (.jobs | type) == "array") then [.[].jobs[]] else empty end' <<<"$raw" > "$cache/$key" 2>/dev/null \
      || { rm -f "$cache/$key"; return 1; }
  fi
  cat "$cache/$key"
}
# The runs of each workflow and event group, newest first: one JSON array of arrays. A run counts when it is completed or is a re-run
# still going (attempt above 1); a first attempt still going waits its turn and is left out.
groups="$(jq -c '
  map(select(.status == "completed" or (.attempt // 1) > 1))
  | group_by([.workflowDatabaseId, .group])
  | map(sort_by(.createdAt) | reverse)' <<<"$judged")" \
  || unknown "could not read the runs"
# The latest counting run per workflow and event group, one JSON array. An empty run (clear_rule.py, the one home of the rule: a green run of
# the push group that ran no check and carries no evidence) is no verdict: the group's latest run that is not empty is. A group with
# none keeps its latest run. One jobs read per green run of the push group, down to the first that is not empty.
rule_events="$(python3 "$here/clear_rule.py" --rule-events)" || unknown "clear_rule.py failed"
newest="[]"
while IFS= read -r g; do
  [ -n "$g" ] || continue
  pick="$(jq -c '.[0]' <<<"$g")"
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    if jq -e --argjson ev "$rule_events" '.conclusion == "success" and (.event | IN($ev[]))' >/dev/null <<<"$r"; then
      id="$(jq -r .databaseId <<<"$r")"
      jobs_of "$id" >/dev/null || unknown "gh api jobs failed"
      python3 "$here/clear_rule.py" --empty-run --event "$(jq -r .event <<<"$r")" "$cache/$id"
      case $? in 0) continue ;; 1) ;; *) unknown "clear_rule.py failed" ;; esac
    fi
    pick="$r"
    break
  done < <(jq -c '.[]' <<<"$g")
  newest="$(jq -c --argjson p "$pick" '. + [$p]' <<<"$newest")"
done < <(jq -c '.[]' <<<"$groups")
# The workflow file at the head of run $1, in $cache/wf-$1 (one read per run); a failed read returns 1.
workflow_of() {
  [ -f "$cache/wf-$1" ] && return 0
  local run path sha
  run="$(jq -c --argjson n "$1" '.[] | select(.databaseId == $n)' <<<"$judged")" || return 1
  path="$(jq -r --argjson i "$(jq .workflowDatabaseId <<<"$run")" '.[] | select(.id == $i) | .path' <<<"$flows")" || return 1
  sha="$(jq -r '.headSha // empty' <<<"$run")"
  { [ -n "$path" ] && [ -n "$sha" ]; } || return 1
  gh api "repos/$GITHUB_REPOSITORY/contents/$path?ref=$sha" -H "Accept: application/vnd.github.raw+json" > "$cache/wf-$1" || { rm -f "$cache/wf-$1"; return 1; }
  [ -s "$cache/wf-$1" ] || { rm -f "$cache/wf-$1"; return 1; }
}
# The job-level timeout-minutes of the job named $2 in workflow file $1: an integer above 0, from the one job whose key or `name:` is
# that name (a matrix suffix ` (...)` is dropped when no job has the full name). Prints 360, GitHub's default cap, when that job has
# no job-level timeout-minutes key. Prints nothing and returns 1 when no single job matches or its cap is no such integer. A job-level key is a line at the indent of the first line under the job key, so a
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
  if (c != 1) exit 1
  if (!(hit in cap)) { print 360; exit 0 }
  if (cap[hit] !~ /^[0-9]+$/ || cap[hit] + 0 < 1) exit 1
  print cap[hit] + 0
}
AWK
)"
cap_of() { awk -v want="$2" "$CAP_AWK" "$1"; }
# cap_ends <run id> <jobs JSON>: the jobs of the run cancelled at their cap, in $ends, one "name<TAB>cap<TAB>minutes" per line; $endunk
# is why a cancelled job could not be judged, or empty. Reads the workflow file only when a job was cancelled.
cap_ends() {
  local lines secs name cap
  ends=""; endunk=""
  # Seconds each cancelled job ran, or "never" (no started_at or completed_at, or a time that does not parse), then its name.
  lines="$(jq -r '.[] | select(.status == "completed" and .conclusion == "cancelled")
    | (try ((.completed_at | fromdateiso8601) - (.started_at | fromdateiso8601)) catch null) as $s
    | "\(if $s == null or $s < 0 then "never" else ($s | floor) end)\t\(.name)"' <<<"$2")" || { endunk="could not read the jobs of run $1"; return 0; }
  [ -n "$lines" ] || return 0
  workflow_of "$1" || { endunk="gh api contents failed for run $1"; return 0; }
  while IFS=$'\t' read -r secs name; do
    if [ "$secs" = never ]; then endunk="job $name of run $1 has no readable start and end time"; continue; fi
    cap="$(cap_of "$cache/wf-$1" "$name")" || { endunk="job $name of run $1 has no single job-level timeout-minutes in its workflow file"; continue; }
    [ "$secs" -ge $((cap * 60)) ] || continue
    ends+="$name"$'\t'"$cap"$'\t'"$((secs / 60))"$'\n'
  done <<<"$lines"
}
# cap_lines <run JSON> <prefix> [suffix]: one line per job in $ends, "<prefix>job NAME ran M min, cap C min, run ID<suffix>".
cap_lines() {
  jq -Rr --argjson r "$1" --arg prefix "$2" --arg suffix "${3:-}" \
    'split("\t") | "\($prefix)job \(.[0]) ran \(.[2]) min, cap \(.[1]) min, run \($r.databaseId)\($suffix)"' <<<"${ends%$'\n'}"
}
# add_ends <run id> <run JSON> <jobs JSON> <attempt> [suffix]: judge one attempt of a run. An attempt with a cap end queues its own
# wake, KEY `cap:<run id>:<attempt>`, under the line $header. Its text names that attempt's cap jobs only, so a later attempt of a run
# whose earlier attempt was reported still wakes. An attempt that cannot be judged sets $capunk. The wakes run after every run was
# judged.
wake_keys=(); wake_shas=(); wake_texts=()
add_ends() {
  cap_ends "$1" "$3"
  [ -z "$endunk" ] || capunk="$endunk"
  [ -n "$ends" ] || return 0
  wake_keys+=("cap:$1:$4"); wake_shas+=("$(jq -r '.headSha // empty' <<<"$2")")
  wake_texts+=("$(printf 'CI job hit its time cap on %s: %s\n\n%s\n%s' "$branch" "${ends%%$'\t'*}" "$header" "$(cap_lines "$2" "  cap end: " "${5:-}")")")
}
# add_newest <run id> <run JSON> <jobs JSON>: add_ends for the run's newest attempt.
add_newest() { add_ends "$1" "$2" "$3" "$(jq -r '.attempt // 1' <<<"$2")"; }
# earlier_attempts <run id> <run JSON> [strict]: add_ends for each attempt before the run's newest. The jobs of an attempt come from
# the attempts endpoint, each read once. An attempt that cannot be read is unknown; with strict, an attempt with no jobs is too.
earlier_attempts() {
  local att ajobs
  for att in $(seq 1 $(($(jq -r '.attempt // 1' <<<"$2") - 1))); do
    ajobs="$(jobs_of "$1" "$att")" || { capunk="gh api attempt jobs failed for run $1 attempt $att"; continue; }
    if [ -n "${3:-}" ] && jq -e 'length == 0' >/dev/null <<<"$ajobs"; then capunk="attempt $att of cancelled run $1 has no jobs"; continue; fi
    add_ends "$1" "$2" "$ajobs" "$att" ", attempt $att"
  done
}
# A group whose newest run is a re-run still going is unknown: never green, never judged by an older run. This soft unknown
# ($capunk) waits until the end, so a cap end or a red run found elsewhere still acts. A hard `unknown` (a failed read in the failed
# loop, below) exits at once, before any queued wake posts; the next cycle reads again.
capunk=""
flight="$(jq -r '[.[] | select(.status != "completed") | "\(.workflowName) run \(.databaseId) (attempt \(.attempt), \(.status))"] | join("; ")' <<<"$newest")" \
  || unknown "could not read the runs"
[ -z "$flight" ] || capunk="re-run in flight: $flight"
# Every failed run of the window is judged for a cap end, one jobs read each (see the header). Only the newest run of a group can be
# red, and not when a clearing run N exists.
red=""
redrun=""
failed="$(jq -c '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure")' <<<"$judged")" \
  || unknown "could not read the runs"
newest_ids="$(jq -c 'map(.databaseId)' <<<"$newest")" || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  rid="$(jq -r .databaseId <<<"$r")"
  if ! jq -e --argjson ids "$newest_ids" '.databaseId as $i | $ids | index($i)' >/dev/null <<<"$r"; then
    # A newer run of its group supersedes it: never red, but a cap end in any attempt still wakes.
    header="$(jq -r '"- \(.workflowName) (\(.conclusion), superseded by a newer run of its group): \(.url)"' <<<"$r")"
    if rjobs="$(jobs_of "$rid")"; then add_newest "$rid" "$r" "$rjobs"; else capunk="gh api jobs failed for run $rid"; fi
    earlier_attempts "$rid" "$r"
    continue
  fi
  cands="$(jq -r --argjson r "$r" '.[] | select(.workflowDatabaseId == $r.workflowDatabaseId and .group != $r.group
    and .createdAt > $r.createdAt and .conclusion == "success") | .databaseId' <<<"$newest")" || unknown "could not read the runs"
  cleared=""
  if [ -n "$cands" ]; then
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
        case $? in 0) cleared=1; break ;; 1) ;; *) unknown "clear_rule.py failed" ;; esac
      done <<<"$cands"
    fi
  fi
  if [ -n "$cleared" ]; then
    # Not red: its red jobs are cleared. Its cap end, in any attempt, still wakes.
    header="$(jq -r '"- \(.workflowName) (\(.conclusion), its red jobs cleared by a newer green run): \(.url)"' <<<"$r")"
    add_newest "$rid" "$r" "$rjobs"
    earlier_attempts "$rid" "$r"
    continue
  fi
  header="$(jq -r '"- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$r")"
  red+="$header"$'\n'
  redrun=1
  # The run is red by its conclusion whatever its jobs say: a cap end in any attempt wakes, and an unreadable read drops it.
  if rjobs="$(jobs_of "$rid")"; then add_newest "$rid" "$r" "$rjobs"; fi
  earlier_attempts "$rid" "$r"
done <<<"$failed"
# Cancelled runs: a job of the run cancelled at its cap wakes its run (see the header). Every cancelled run in the window is judged,
# not only the newest of its group. An unknown waits until the end, so a red run or a cap end found elsewhere still acts.
cancelled="$(jq -c '.[] | select(.conclusion == "cancelled")' <<<"$judged")" || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  rid="$(jq -r .databaseId <<<"$r")"
  rjobs="$(jobs_of "$rid")" || { capunk="gh api jobs failed for run $rid"; continue; }
  if jq -e 'length == 0' >/dev/null <<<"$rjobs"; then capunk="cancelled run $rid has no jobs"; continue; fi
  header="$(jq -r '"- \(.workflowName) (cancelled): \(.url)"' <<<"$r")"
  add_newest "$rid" "$r" "$rjobs"
  earlier_attempts "$rid" "$r" strict
done <<<"$cancelled"
# A succeeded run that was re-run: a cap end in an earlier attempt wakes like any other cap end on the branch. A failed read is unknown.
reruns="$(jq -c '.[] | select(.conclusion == "success" and (.attempt // 1) > 1)' <<<"$judged")" || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  rid="$(jq -r .databaseId <<<"$r")"
  header="$(jq -r '"- \(.workflowName) (succeeded on a later attempt): \(.url)"' <<<"$r")"
  earlier_attempts "$rid" "$r"
done <<<"$reruns"
red="${red%$'\n'}"
if [ -z "$redrun" ] && [ "${#wake_keys[@]}" = 0 ]; then
  [ -z "$capunk" ] || unknown "$capunk"
  echo green; exit 0
fi
# A red run opens the issue through issue.sh, which prints nothing on success and `unknown` plus a warning when the write fails. The
# issue names the red runs and no cap end. A cap end with no red run opens none. Each cap-end attempt is then woken whatever the
# verdict. wake.sh's stdout would break the verdict line, so it goes to stderr.
verdict=alarm
if [ -n "$redrun" ]; then
  verdict=red
  res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'CI alarm on %s:\n\n%s' "$branch" "$red")")"
  if grep -qx unknown <<<"$res"; then verdict="$res"; fi
fi
unwoken=""
for i in "${!wake_keys[@]}"; do
  REPO="$GITHUB_REPOSITORY" SHA="${wake_shas[$i]}" KEY="${wake_keys[$i]}" TEXT="${wake_texts[$i]}" bash "$here/wake.sh" >&2 \
    || unwoken+="${unwoken:+, }${wake_keys[$i]#cap:}"
done
echo "$verdict"
[ -z "$unwoken" ] || { echo "::error::ci-alarm: the cap end of run:attempt $unwoken could not be woken" >&2; exit 1; }
