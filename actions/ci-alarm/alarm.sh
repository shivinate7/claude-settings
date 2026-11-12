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
# Cap end (owner, page item 549 a, 12:07 CST Nov 12; judged in every run of the window, coordinator pick 12:26 CST): a job cancelled
# at its cap ran at least its job-level `timeout-minutes` (completed_at - started_at, from the jobs read), the cap read from the run's
# workflow file at its head. A job with no job-level `timeout-minutes` has GitHub's default cap, 360 minutes. Every such job is named
# and its run is woken, wherever it sits:
#   - in any cancelled run of the window, newest of its group or not, and in each earlier attempt of it;
#   - in any earlier attempt of a succeeded re-run;
#   - in a failed run, in its newest attempt or an earlier one, whether a newer green run clears the run or not.
# The clear drops a run's red jobs, never its cap end. The merge gate (merge.py base_state) leaves a run with no red job and a job timed
# out at a job-level cap it finds in its checkout out of red and out of unknown; a cancelled run reads UNKNOWN there for a job with no
# job-level cap or a cap it does not find, and a failure run reads red. The alarm is the signal, since a cap end is not a red job.
# A job cancelled under its cap (a person, or an earlier failure) stays quiet. A cancelled job with no started_at, a non-integer cap
# (an expression), no single job of that name in the file, a cancelled run or an earlier attempt of it with no jobs, or a failed read
# is unknown, never red and never clear.
# Verdict: "red" when a failure run with a red job, not cleared, is named. That run opens the issue "CI red on BRANCH" through issue.sh,
# and every cap end is named in its body. Else "alarm" (a cap end and no red run), which opens no issue (owner R53, 13:07 CST Nov 12).
# Each run with a cap end, in either verdict, is woken through wake.sh (coordinator pick, 13:12 CST): SHA is the run's head commit, KEY
# is `cap:<run id>`, and TEXT opens with "CI job hit its time cap on BRANCH: JOB", the first cap job of that run, then names the run's
# cap ends. wake.sh posts on the merged pull request into main that holds the commit, once per KEY (its hidden marker is the memory), so
# a cap end already reported is not reported again (coordinator ruling, 12:58 CST). A run whose commit has no such pull request cannot
# be woken: wake.sh exits non-zero, and after every run was handled this script prints its verdict and exits 1, naming the run id.
# A failed read or write is unknown, never red.
# Cost: one runs read and the workflows-list read. One jobs read per judged run: each cancelled run of the window, and the newest run of
# a group that failed. One jobs read per earlier attempt of a cancelled, failed or succeeded re-run. One workflow-file read per run
# with a cancelled job, once. A clear candidate N adds one jobs read, and one contents read of N's workflow file at N's head (headSha)
# unless N leaves a red job of R unpassed (a certain red), and two clear_rule.py starts at most. Each woken run adds one pulls read, one
# comments read of its pull request and at most one comment write (wake.sh). No long-lived process starts: short jq, awk, gh and python3
# processes run, and the only files written are temp cache files in a folder this script removes on exit.
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
# Latest run per workflow and event group, one JSON array. A run counts when it is completed or is a re-run still going (attempt
# above 1); a first attempt still going waits its turn and is left out.
newest="$(jq -c '
  map(select(.status == "completed" or (.attempt // 1) > 1))
  | group_by([.workflowDatabaseId, .group])
  | map(sort_by(.createdAt) | last)' <<<"$judged")" \
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
# add_ends <run id> <run JSON> <jobs JSON> [suffix]: the cap ends of one attempt of a run, added to $capl (the lines of the run being
# judged) and $runfirst (the first cap job of that run); an attempt that cannot be judged sets $capunk.
add_ends() {
  cap_ends "$1" "$3"
  [ -z "$endunk" ] || capunk="$endunk"
  [ -n "$ends" ] || return 0
  [ -n "$runfirst" ] || runfirst="${ends%%$'\t'*}"
  capl+="$(cap_lines "$2" "  cap end: " "${4:-}")"$'\n'
}
# earlier_attempts <run id> <run JSON> [strict]: add_ends for each attempt before the run's newest. The jobs of an attempt come from
# the attempts endpoint, each read once. An attempt that cannot be read is unknown; with strict, an attempt with no jobs is too.
earlier_attempts() {
  local att ajobs
  for att in $(seq 1 $(($(jq -r '.attempt // 1' <<<"$2") - 1))); do
    ajobs="$(jobs_of "$1" "$att")" || { capunk="gh api attempt jobs failed for run $1 attempt $att"; continue; }
    if [ -n "${3:-}" ] && jq -e 'length == 0' >/dev/null <<<"$ajobs"; then capunk="attempt $att of cancelled run $1 has no jobs"; continue; fi
    add_ends "$1" "$2" "$ajobs" ", attempt $att"
  done
}
# wake_add <run id> <run JSON> <header line>: queue the wake of a run whose attempts held a cap end, from its $capl and $runfirst; a
# run with none queues nothing. The wakes run after every run was judged.
wake_ids=(); wake_shas=(); wake_texts=()
wake_add() {
  [ -n "$capl" ] || return 0
  wake_ids+=("$1"); wake_shas+=("$(jq -r '.headSha // empty' <<<"$2")")
  wake_texts+=("$(printf 'CI job hit its time cap on %s: %s\n\n%s\n%s' "$branch" "$runfirst" "$3" "${capl%$'\n'}")")
}
# A group whose newest run is a re-run still going is unknown: never green, never judged by an older run. Like every unknown it waits
# until the end, so an alarm found elsewhere still wakes its run.
capunk=""
flight="$(jq -r '[.[] | select(.status != "completed") | "\(.workflowName) run \(.databaseId) (attempt \(.attempt), \(.status))"] | join("; ")' <<<"$newest")" \
  || unknown "could not read the runs"
[ -z "$flight" ] || capunk="re-run in flight: $flight"
# Red = failure, timed_out or startup_failure, unless a clearing run N exists (see the header). A job of it cancelled at its cap is named.
red=""
redrun=""
failed="$(jq -c '.[] | select(.conclusion == "failure" or .conclusion == "timed_out" or .conclusion == "startup_failure")' <<<"$newest")" \
  || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  cands="$(jq -r --argjson r "$r" '.[] | select(.workflowDatabaseId == $r.workflowDatabaseId and .group != $r.group
    and .createdAt > $r.createdAt and .conclusion == "success") | .databaseId' <<<"$newest")" || unknown "could not read the runs"
  rid="$(jq -r .databaseId <<<"$r")"
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
  capl=""; runfirst=""
  if [ -n "$cleared" ]; then
    # Not red: its red jobs are cleared. Its cap end, in any attempt, still alarms, so the run is named only when it has one.
    add_ends "$rid" "$r" "$rjobs"
    earlier_attempts "$rid" "$r"
    header="$(jq -r '"- \(.workflowName) (\(.conclusion), its red jobs cleared by a newer green run): \(.url)"' <<<"$r")"
    [ -z "$capl" ] || red+="$header"$'\n'"${capl%$'\n'}"$'\n'
    wake_add "$rid" "$r" "$header"
    continue
  fi
  header="$(jq -r '"- \(.workflowName) (\(.conclusion)): \(.url)"' <<<"$r")"
  red+="$header"$'\n'
  redrun=1
  # The run is red by its conclusion whatever its jobs say: a job cancelled at its cap, in any attempt, is named under it, and an
  # unreadable read names nothing.
  if rjobs="$(jobs_of "$rid")"; then add_ends "$rid" "$r" "$rjobs"; fi
  earlier_attempts "$rid" "$r"
  red+="$capl"
  wake_add "$rid" "$r" "$header"
done <<<"$failed"
# Cancelled runs: the alarm is raised when a job of the run was cancelled at its cap (see the header). Every cancelled run in the
# window is judged, not only the newest of its group. An unknown waits until the end, so an alarm found here or above still opens
# its issue.
cancelled="$(jq -c '.[] | select(.conclusion == "cancelled")' <<<"$judged")" || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  rid="$(jq -r .databaseId <<<"$r")"
  rjobs="$(jobs_of "$rid")" || { capunk="gh api jobs failed for run $rid"; continue; }
  if jq -e 'length == 0' >/dev/null <<<"$rjobs"; then capunk="cancelled run $rid has no jobs"; continue; fi
  capl=""; runfirst=""
  add_ends "$rid" "$r" "$rjobs"
  earlier_attempts "$rid" "$r" strict
  header="$(jq -r '"- \(.workflowName) (cancelled): \(.url)"' <<<"$r")"
  [ -z "$capl" ] || red+="$header"$'\n'"${capl%$'\n'}"$'\n'
  wake_add "$rid" "$r" "$header"
done <<<"$cancelled"
# A succeeded run that was re-run: a cap end in an earlier attempt alarms like any other cap end on the branch. A failed read is unknown.
reruns="$(jq -c '.[] | select(.conclusion == "success" and (.attempt // 1) > 1)' <<<"$judged")" || unknown "could not read the runs"
while IFS= read -r r; do
  [ -n "$r" ] || continue
  rid="$(jq -r .databaseId <<<"$r")"
  capl=""; runfirst=""
  earlier_attempts "$rid" "$r"
  header="$(jq -r '"- \(.workflowName) (succeeded on a later attempt): \(.url)"' <<<"$r")"
  [ -z "$capl" ] || red+="$header"$'\n'"${capl%$'\n'}"$'\n'
  wake_add "$rid" "$r" "$header"
done <<<"$reruns"
red="${red%$'\n'}"
if [ -z "$red" ] && [ -n "$capunk" ]; then unknown "$capunk"; fi
if [ -z "$red" ]; then echo green; exit 0; fi
# A red run opens the issue through issue.sh, which prints nothing on success and `unknown` plus a warning when the write fails. A cap
# end with no red run opens none. Each cap-end run is then woken whatever the verdict. wake.sh's stdout would break the verdict
# line, so it goes to stderr.
verdict=alarm
if [ -n "$redrun" ]; then
  verdict=red
  res="$(bash "$here/issue.sh" "CI red on $branch" "$(printf 'CI alarm on %s:\n\n%s' "$branch" "$red")")"
  if grep -qx unknown <<<"$res"; then verdict="$res"; fi
fi
unwoken=""
for i in "${!wake_ids[@]}"; do
  REPO="$GITHUB_REPOSITORY" SHA="${wake_shas[$i]}" KEY="cap:${wake_ids[$i]}" TEXT="${wake_texts[$i]}" bash "$here/wake.sh" >&2 \
    || unwoken+="${unwoken:+, }${wake_ids[$i]}"
done
echo "$verdict"
[ -z "$unwoken" ] || { echo "::error::ci-alarm: the cap end of run $unwoken could not be woken" >&2; exit 1; }
