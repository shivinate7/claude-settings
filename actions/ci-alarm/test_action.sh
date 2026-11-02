#!/usr/bin/env bash
# Red run with a fake `gh`. Each (workflow, event group) judges its newest run: a red group opens the
# issue. A green run of another group clears it only when that run is newer, is the newest of its group,
# succeeded, and passed every job of the red run. Runs of an event not in events.json, and of a deleted
# or absent workflow, are not judged. A failed read or write prints `unknown` and exits 0.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
tmp="$work/case"; mkdir -p "$tmp/bin"
# Fake gh. FAIL is a glob over "$1 $2"; a call that matches it exits 1. EMPTY is a glob too; a call
# that matches it exits 0 with no output. `run list` keeps only the --json fields it is asked for and
# the runs of the --status it is asked for, as gh does; unparsable runs are echoed raw. `api` routes
# the jobs of a run to $JOBS/<run id> and records each such read in $READS; a run with no jobs fixture
# fails the read, so an unexpected read is unknown.
cat > "$tmp/bin/gh" <<'SH'
#!/usr/bin/env bash
if [ -n "${FAIL:-}" ] && [[ "$1 $2" == $FAIL ]]; then echo "gh: HTTP 500 (fake)" >&2; exit 1; fi
if [ -n "${EMPTY:-}" ] && [[ "$1 $2" == $EMPTY ]]; then exit 0; fi
case "$1 $2" in
  "run list")
    want="$(printf '%s\n' "$@" | sed -n '/^--json$/{n;p;}')"
    status="$(printf '%s\n' "$@" | sed -n '/^--status$/{n;p;}')"
    jq --arg want "$want" --arg status "$status" '[.[] | select($status == "" or .status == $status) | with_entries(select(.key as $k | $want | split(",") | any(. == $k)))]' "$RUNS" 2>/dev/null || cat "$RUNS" ;;
  api*)
    case "$2" in
      */actions/runs/*/jobs*)
        id="${2#*actions/runs/}"; id="${id%%/*}"
        echo "$2" >> "${READS:-/dev/null}"
        if [ -f "${JOBS:-/nonexistent}/$id" ]; then cat "$JOBS/$id"; else echo "gh: no jobs fixture for run $id (fake)" >&2; exit 1; fi ;;
      *) cat "$WORKFLOWS" ;;
    esac ;;
  "issue list") echo "${OPEN:-}" ;;
  "issue create") echo "ISSUE $*" >> "$LOG" ;;
  "issue comment") echo "COMMENT $*" >> "$LOG" ;;
esac
SH
chmod +x "$tmp/bin/gh"
# Fixture, one home. gh_run prints one run as `gh run list --json` returns it: args are workflow,
# conclusion (null for a run still going), createdAt, url, event, databaseId (the run id) and status
# (completed unless given). Workflow ids: ci 1, deploy 2, alarm 3, pages 4, old 5 (deleted),
# gone 6 (absent from the list), late 7 (on page two of the workflows list), dman 8 and dinact 9
# (disabled, on page two), links 10 (on page two).
gh_run() {
  local id concl
  case "$1" in ci) id=1 ;; deploy) id=2 ;; alarm) id=3 ;; pages) id=4 ;; old) id=5 ;; gone) id=6 ;; late) id=7 ;;
    dman) id=8 ;; dinact) id=9 ;; links) id=10 ;; esac
  concl="\"$2\""; [ "$2" = null ] && concl=null
  printf '{"workflowName":"%s","workflowDatabaseId":%s,"databaseId":%s,"conclusion":%s,"createdAt":"%s","url":"%s","event":"%s","status":"%s"}\n' \
    "$1" "$id" "$6" "$concl" "$3" "$4" "$5" "${7:-completed}"
}
# A case starts with its runs: runs_are clears the jobs of the case before the jobs_of lines that follow it.
runs_are() { printf '%s\n' "$@" | jq -s . > "$tmp/runs"; rm -rf "$tmp/jobs"; mkdir -p "$tmp/jobs"; }
# jobs_of <run id> [job:conclusion]...: the jobs of one run as `gh api .../actions/runs/<id>/jobs` lists them.
jobs_of() {
  local id="$1"; shift
  printf '%s\n' "$@" | jq -Rs 'split("\n") | map(select(length > 0) | split(":") | {name: .[0], status: "completed", conclusion: .[1]}) | {total_count: length, jobs: .}' > "$tmp/jobs/$id"
}
# The workflows list as `gh api --paginate` prints it: one JSON document per page.
cat > "$tmp/workflows" <<'JSON'
{"total_count": 7, "workflows": [
  {"id": 1, "name": "ci", "path": ".github/workflows/ci.yml", "state": "active"},
  {"id": 2, "name": "deploy", "path": ".github/workflows/deploy.yml", "state": "active"},
  {"id": 3, "name": "alarm", "path": ".github/workflows/alarm.yml", "state": "active"},
  {"id": 4, "name": "pages build and deployment", "path": "dynamic/pages/pages-build-deployment", "state": "active"},
  {"id": 5, "name": "old", "path": ".github/workflows/old.yml", "state": "deleted"}]}
{"total_count": 9, "workflows": [
  {"id": 7, "name": "late", "path": ".github/workflows/late.yml", "state": "active"},
  {"id": 8, "name": "dman", "path": ".github/workflows/dman.yml", "state": "disabled_manually"},
  {"id": 9, "name": "dinact", "path": ".github/workflows/dinact.yml", "state": "disabled_inactivity"},
  {"id": 10, "name": "links", "path": ".github/workflows/links.yml", "state": "active"}]}
JSON
bad=0
t() { # want label [FAIL glob] [EMPTY glob] [text the issue must name] [jobs reads: "none", or the run paths read, in any order]
  : > "$tmp/log"; : > "$tmp/reads"
  out="$(PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" JOBS="$tmp/jobs" READS="$tmp/reads" LOG="$tmp/log" \
    FAIL="${3:-}" EMPTY="${4:-}" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" 2>"$tmp/err")"
  code=$?
  shown="$(grep -v '^::warning::' <<<"$out")" # the verdict, without annotations
  ok=0
  case "$1" in
    green) [ "$shown" = green ] && [ ! -s "$tmp/log" ] && ok=1 ;;
    red) [ "$shown" = red ] && grep -q ISSUE "$tmp/log" && ok=1 ;;
    unknown) [ "$shown" = unknown ] && [ ! -s "$tmp/log" ] && grep -q '::warning::' <<<"$out"$'\n'"$(cat "$tmp/err")" && ok=1 ;;
  esac
  [ "$code" = 0 ] || ok=0
  if [ -n "${5:-}" ] && ! grep -qF -- "$5" "$tmp/log"; then ok=0; fi
  if [ -n "${6:-}" ]; then
    expect_reads="$(tr ' ' '\n' <<<"$6" | grep -v '^none$' | sort | tr '\n' ' ')"
    got_reads="$(grep -o 'actions/runs/[0-9]*/jobs' "$tmp/reads" | sort | tr '\n' ' ')"
    [ "$expect_reads" = "$got_reads" ] || ok=0
  fi
  if [ "$ok" = 1 ]; then echo "ok   $2"; else echo "FAIL $2 (exit $code, got: $out; jobs reads: $(tr '\n' ' ' < "$tmp/reads"))"; bad=1; fi
}
runs_are "$(gh_run ci failure 2026-01-02 u1 push 1)" "$(gh_run ci success 2026-01-01 u0 push 2)"
t red latest-red-opens-issue
runs_are "$(gh_run ci success 2026-01-02 u1 push 1)" "$(gh_run ci failure 2026-01-01 u0 push 2)"
t green red-then-fixed-is-quiet
runs_are "$(gh_run alarm failure 2026-01-02 u1 push 1)"
t green own-workflow-is-ignored
runs_are "$(gh_run ci success 2026-01-02 u1 push 1)" "$(gh_run deploy timed_out 2026-01-01 u2 push 2)"
t red one-red-workflow-among-green

# A red run is cleared by a newer green run of the other group only when that run passes every job of the red run.
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 push 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks:failure
jobs_of 2 scope:success
t red red-schedule-is-not-cleared-by-a-newer-green-push-without-its-job "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks:failure
jobs_of 2 scope:success
t red red-schedule-is-not-cleared-by-a-newer-green-dispatch-without-its-job "" "" https://runs/red-1
runs_are "$(gh_run links success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run links failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 readme-links:failure
jobs_of 2 readme-links:success
t green joyous-red-schedule-is-cleared-by-a-newer-green-dispatch-with-its-job "" "" "" "actions/runs/1/jobs actions/runs/2/jobs"
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure scope:success
jobs_of 2 checks:success scope:success
t green red-push-is-cleared-by-a-newer-green-schedule-with-every-job "" "" "" "actions/runs/1/jobs actions/runs/2/jobs"
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks-macos:failure
jobs_of 2 checks:success
t red green-job-named-by-a-prefix-of-the-red-job-does-not-clear-it "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks:failure
jobs_of 2 checks-macos:success
t red green-job-named-by-a-longer-name-does-not-clear-it "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 old-checks:failure
jobs_of 2 checks:success
t red green-job-named-by-a-suffix-of-the-red-job-does-not-clear-it "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks:failure
jobs_of 2 checks:skipped
t red red-job-skipped-in-the-green-run-does-not-clear-it "" "" https://runs/red-1
for concl in cancelled neutral skipped timed_out; do
  runs_are "$(gh_run ci "$concl" 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
  jobs_of 1 checks:failure
  jobs_of 2 checks:success
  t red "green-run-concluded-$concl-clears-nothing" "" "" https://runs/red-1
done
runs_are "$(gh_run ci null 2026-01-02 https://runs/green-2 workflow_dispatch 2 in_progress)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
t red green-run-still-going-clears-nothing "" "" https://runs/red-1 none
runs_are "$(gh_run ci failure 2026-01-03 https://runs/red-3 schedule 3)" "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
jobs_of 3 checks:failure
t red green-run-that-is-not-the-newest-of-its-group-clears-nothing "" "" https://runs/red-1 none
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)" "$(gh_run ci success 2026-01-01 https://runs/green-2 schedule 2)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
t red green-run-older-than-the-red-run-clears-nothing "" "" https://runs/red-1 none
runs_are "$(gh_run ci startup_failure 2026-01-02 https://runs/red-1 push 1)" "$(gh_run ci success 2026-01-03 https://runs/green-2 schedule 2)"
jobs_of 1
jobs_of 2 checks:success
t red red-run-with-no-jobs-is-not-cleared-across-groups "" "" https://runs/red-1
# A failed run with no red job (its only job passed, was cancelled short, or was skipped) is not cleared across groups.
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:success
jobs_of 2 checks:success
t red failed-run-whose-only-job-passed-is-not-cleared-across-groups "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:cancelled
jobs_of 2 checks:success
t red failed-run-whose-only-job-was-cancelled-is-not-cleared-across-groups "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:skipped
jobs_of 2 checks:success
t red failed-run-whose-only-job-was-skipped-is-not-cleared-across-groups "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 schedule 1)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
t unknown green-runs-jobs-read-fails-is-unknown "api *actions/runs/2/jobs*"
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
t red red-run-with-no-candidate-reads-no-jobs "" "" https://runs/red-1 none
runs_are "$(gh_run ci cancelled 2026-01-02 u1 push 1)"
t green cancelled-run-is-not-red "" "" "" none
runs_are "$(gh_run ci success 2026-01-02 u1 schedule 2)" "$(gh_run ci failure 2026-01-01 u0 schedule 1)"
t green red-schedule-is-cleared-by-a-newer-green-schedule "" "" "" none
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 u0 push 1)"
t green red-push-is-cleared-by-a-newer-green-dispatch "" "" "" none
runs_are "$(gh_run pages failure 2026-01-02 u1 dynamic 1)"
t green failed-pages-build-is-not-judged
runs_are "$(gh_run old failure 2026-01-02 u1 push 1)"
t green red-run-of-a-deleted-workflow-is-not-judged
runs_are "$(gh_run gone failure 2026-01-02 u1 push 1)"
t green red-run-of-an-absent-workflow-is-not-judged
runs_are "$(gh_run late failure 2026-01-02 u1 push 1)"
t red red-run-of-a-workflow-on-page-two-is-judged
runs_are "$(gh_run dman failure 2026-01-02 u1 push 1)"
t red red-run-of-a-manually-disabled-workflow-is-judged
runs_are "$(gh_run dinact failure 2026-01-02 u1 push 1)"
t red red-run-of-an-inactivity-disabled-workflow-is-judged
runs_are "$(gh_run ci failure 2026-01-02 u1 push 1)"
t unknown run-list-fails-is-unknown "run list"
t unknown run-list-with-empty-stdout-is-unknown "" "run list"
printf 'not json' > "$tmp/runs"
t unknown run-list-that-is-not-json-is-unknown
printf '[1]' > "$tmp/runs"  # an array passes the list check, but its element is no run: the jq that reads the runs fails
t unknown run-list-of-non-runs-is-unknown
runs_are "$(gh_run ci failure 2026-01-02 u1 push 1)"
t unknown workflow-list-fails-is-unknown "api *actions/workflows*"
t unknown workflow-list-with-empty-stdout-is-unknown "" "api *actions/workflows*"
t unknown issue-create-fails-is-unknown-exit-0 "issue create"
: > "$tmp/log"
OPEN=42 PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" LOG="$tmp/log" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" >/dev/null 2>&1
if grep -q "COMMENT issue comment 42" "$tmp/log" && ! grep -q ISSUE "$tmp/log"; then echo "ok   open-issue-gets-a-comment-not-a-duplicate"
else echo "FAIL open-issue-gets-a-comment-not-a-duplicate"; bad=1; fi
exit $bad
