#!/usr/bin/env bash
# Red run with a fake `gh`. Each (workflow, event group) judges its newest run: a red group opens the
# issue, unless a newer completed run of the other group passed every job the red run ran (`gh api
# --paginate` gives the jobs, one JSON document per page). Runs of an event not in events.json, and of a
# deleted or absent workflow, are not judged. A failed read or write prints `unknown` and exits 0.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
tmp="$work/case"; mkdir -p "$tmp/bin"
# Fake gh. FAIL is a glob over "$1 $2" or over the whole command line; a call that matches it exits 1. EMPTY
# is a glob too, matched the same way; a call that matches it exits 0 with no output. `run list` keeps only
# the --json fields it is asked for, as gh does; unparsable runs are echoed raw. The jobs of a run come from
# `api .../actions/runs/<id>/jobs`, every page of the fixture. The fake's `run view`, the old jobs read, prints
# page one only: a case whose passing job sits on page two fails on that read for that reason alone.
cat > "$tmp/bin/gh" <<'SH'
#!/usr/bin/env bash
if [ -n "${FAIL:-}" ] && { [[ "$1 $2" == $FAIL ]] || [[ "$*" == $FAIL ]]; }; then echo "gh: HTTP 500 (fake)" >&2; exit 1; fi
if [ -n "${EMPTY:-}" ] && { [[ "$1 $2" == $EMPTY ]] || [[ "$*" == $EMPTY ]]; }; then exit 0; fi
case "$1 $2" in
  "run list")
    want="$(printf '%s\n' "$@" | sed -n '/^--json$/{n;p;}')"
    jq --arg want "$want" '[.[] | with_entries(select(.key as $k | $want | split(",") | any(. == $k)))]' "$RUNS" 2>/dev/null || cat "$RUNS" ;;
  api*)
    case "$*" in
      *"actions/runs/"*"/jobs"*)
        rid="$(printf '%s\n' "$@" | sed -n 's#.*actions/runs/\([0-9]*\)/jobs.*#\1#p' | head -1)"
        cat "$JOBS/$rid.json" 2>/dev/null || { echo "gh: no jobs fixture for run $rid (fake)" >&2; exit 1; } ;;
      *) cat "$WORKFLOWS" ;;
    esac ;;
  "run view")
    rid="$(printf '%s\n' "$@" | grep -m1 -E '^[0-9]+$')"
    jq -c -s '.[0]' "$JOBS/$rid.json" 2>/dev/null || { echo "gh: no jobs fixture for run $rid (fake)" >&2; exit 1; } ;;
  "issue list") echo "${OPEN:-}" ;;
  "issue create") echo "ISSUE $*" >> "$LOG" ;;
  "issue comment") echo "COMMENT $*" >> "$LOG" ;;
esac
SH
chmod +x "$tmp/bin/gh"
# Fixture, one home. gh_run prints one run as `gh run list --json` returns it: args are workflow,
# conclusion, createdAt, url, event. Ids: ci 1, deploy 2, alarm 3, pages 4, old 5 (deleted),
# gone 6 (absent from the list), late 7 (on page two of the workflows list), dman 8 and dinact 9
# (disabled, on page two). databaseId is the run's own id: 100 plus the number in its url tag
# (u1 is run 101), so jobs_of keys a run's jobs on the same tag.
run_id() { echo $((100 + ${1#u})); }
gh_run() {
  local id
  case "$1" in ci) id=1 ;; deploy) id=2 ;; alarm) id=3 ;; pages) id=4 ;; old) id=5 ;; gone) id=6 ;; late) id=7 ;;
    dman) id=8 ;; dinact) id=9 ;; esac
  printf '{"workflowName":"%s","workflowDatabaseId":%s,"databaseId":%s,"conclusion":"%s","createdAt":"%s","url":"%s","event":"%s"}\n' "$1" "$id" "$(run_id "$4")" "$2" "$3" "$4" "$5"
}
# A new set of runs drops the jobs of the last case, so a fixture cannot leak into the next one.
runs_are() { rm -rf "$tmp/jobs"; printf '%s\n' "$@" | jq -s . > "$tmp/runs"; }
# The jobs of one run, as `gh api --paginate` prints them: one JSON document per page, `{"total_count": N, "jobs": [...]}`.
# Args: optionally `--per-page K` (K jobs to a page; one page when absent), then the run's url tag, then one
# name:conclusion per job.
jobs_of() {
  local per=0
  if [ "${1:-}" = --per-page ]; then per="$2"; shift 2; fi
  local tag="$1"; shift
  mkdir -p "$tmp/jobs"
  jq -n -c --argjson per "$per" --args '
    [$ARGS.positional[] | split(":") | {name: .[0], conclusion: .[1], status: "completed"}] as $all
    | (if $per > 0 then [range(0; $all | length; $per) as $i | $all[$i:$i + $per]] else [$all] end)
    | .[] | {total_count: ($all | length), jobs: .}' "$@" > "$tmp/jobs/$(run_id "$tag").json"
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
  {"id": 9, "name": "dinact", "path": ".github/workflows/dinact.yml", "state": "disabled_inactivity"}]}
JSON
bad=0
t() { # want label [FAIL glob for the fake gh] [EMPTY glob for the fake gh]
  : > "$tmp/log"
  out="$(PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" JOBS="$tmp/jobs" LOG="$tmp/log" FAIL="${3:-}" EMPTY="${4:-}" \
    GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" 2>"$tmp/err")"
  code=$?
  shown="$(grep -v '^::warning::' <<<"$out")" # the verdict, without annotations
  ok=0
  case "$1" in
    green) [ "$shown" = green ] && [ ! -s "$tmp/log" ] && ok=1 ;;
    red) [ "$shown" = red ] && grep -q ISSUE "$tmp/log" && ok=1 ;;
    unknown) [ "$shown" = unknown ] && [ ! -s "$tmp/log" ] && grep -q '::warning::' <<<"$out"$'\n'"$(cat "$tmp/err")" && ok=1 ;;
  esac
  [ "$code" = 0 ] || ok=0
  if [ "$ok" = 1 ]; then echo "ok   $2"; else echo "FAIL $2 (exit $code, got: $out)"; bad=1; fi
}
runs_are "$(gh_run ci failure 2026-01-02 u1 push)" "$(gh_run ci success 2026-01-01 u0 push)"
t red latest-red-opens-issue
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 push)"
t green red-then-fixed-is-quiet
runs_are "$(gh_run alarm failure 2026-01-02 u1 push)"
t green own-workflow-is-ignored
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run deploy timed_out 2026-01-01 u2 push)"
t red one-red-workflow-among-green
# A red run is cleared by a newer completed run of the other event group that passed every job the red run
# ran. Each case sets the jobs of both runs after runs_are, as name:conclusion.
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:success nightly:failure
jobs_of u1 checks:success nightly:skipped
t red red-schedule-is-not-cleared-by-a-newer-green-push
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 scope:success
t red red-schedule-is-not-cleared-by-a-newer-green-dispatch
runs_are "$(gh_run ci success 2026-01-02 u1 schedule)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
t green red-schedule-is-cleared-by-a-newer-green-schedule
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch)" "$(gh_run ci failure 2026-01-01 u0 push)"
jobs_of u0 checks:failure
jobs_of u1 checks:success
t green red-push-is-cleared-by-a-newer-green-dispatch
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 readme-links:failure checks:success
jobs_of u1 readme-links:success checks:success
t green red-schedule-is-cleared-by-a-newer-green-dispatch-with-the-same-jobs
runs_are "$(gh_run ci success 2026-01-02 u1 schedule)" "$(gh_run ci failure 2026-01-01 u0 push)"
jobs_of u0 readme-links:failure checks:success
jobs_of u1 readme-links:success checks:success
t green red-push-is-cleared-by-a-newer-green-schedule-with-the-same-jobs
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 checks:success scope:success
t green red-schedule-is-cleared-by-a-newer-green-push-with-extra-jobs
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure scope:skipped
jobs_of u1 checks:success
t green red-schedule-skipped-job-is-not-needed-in-the-newer-run
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure checks-macos:cancelled
jobs_of u1 checks:success
t red red-schedule-cancelled-job-must-pass-in-the-newer-run
runs_are "$(gh_run ci cancelled 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 checks:success
t red red-schedule-is-not-cleared-by-a-newer-cancelled-push
runs_are "$(gh_run ci failure 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 checks:failure
t red red-schedule-is-not-cleared-by-a-newer-red-push
runs_are "$(gh_run ci "" 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
t red red-schedule-is-not-cleared-by-a-newer-push-in-progress
runs_are "$(gh_run ci failure 2026-01-02 u0 schedule)" "$(gh_run ci success 2026-01-01 u1 push)"
jobs_of u0 checks:failure
jobs_of u1 checks:success
t red red-schedule-is-not-cleared-by-an-older-green-push
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 checks-macos:success
t red red-schedule-is-not-cleared-by-a-job-whose-name-only-starts-with-it
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 checks:success checks:failure
t red red-schedule-is-not-cleared-by-a-newer-push-with-a-failed-duplicate-job
# A red run with no non-skipped job clears nothing: the newer green push is not enough (clears.py, an empty job set).
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci startup_failure 2026-01-01 u0 schedule)"
jobs_of u0
jobs_of u1 checks:success
t red red-run-with-no-job-is-not-cleared-by-a-newer-green-push
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:skipped
jobs_of u1 checks:success
t red red-run-with-only-skipped-jobs-is-not-cleared-by-a-newer-green-push
# The newer push run's passing job is on page two of its jobs: the read must take every page to clear the red run.
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of --per-page 2 u1 lint:success scope:success checks:success
t green newer-push-with-its-passing-job-on-page-two-clears-the-red-run
# A jobs list over 128 KB is still judged: Linux caps one argv string at 128 KB, and clears.py takes each job list as one.
long=(checks:success)
for i in $(seq 1 2000); do long+=("long-job-$(printf '%04d' "$i")-$(printf '%0100d' 0):success"); done
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 checks:failure
jobs_of u1 "${long[@]}"
if [ "$(wc -c < "$tmp/jobs/$(run_id u1).json")" -gt 131072 ]; then echo "ok   the 2000-job fixture is over 128 KB"
else echo "FAIL the 2000-job fixture is not over 128 KB"; bad=1; fi
t green newer-push-with-a-jobs-list-over-128-kb-is-judged
# Two workflows: the read of one candidate fails. The other red run, with no candidate, still opens the issue.
runs_are "$(gh_run ci failure 2026-01-02 u1 push)" "$(gh_run deploy failure 2026-01-01 u2 schedule)" "$(gh_run deploy success 2026-01-02 u3 push)"
jobs_of u2 checks:failure
t red failed-jobs-read-of-one-candidate-does-not-hide-another-red-run "api *actions/runs/103/jobs*"
if grep -q 'ci (failure): u1' "$tmp/log"; then echo "ok   the open issue names the red run that has no candidate"
else echo "FAIL the open issue does not name the red run that has no candidate"; bad=1; fi
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
jobs_of u0 readme-links:failure checks:success
jobs_of u1 readme-links:success checks:success
# "*jobs*" matches a jobs read on either route: the api pages the alarm reads now, and the old `run view`.
t unknown jobs-read-fails-is-unknown "*jobs*"
t unknown jobs-read-with-empty-stdout-is-unknown "" "*jobs*"
runs_are "$(gh_run pages failure 2026-01-02 u1 dynamic)"
t green failed-pages-build-is-not-judged
runs_are "$(gh_run old failure 2026-01-02 u1 push)"
t green red-run-of-a-deleted-workflow-is-not-judged
runs_are "$(gh_run gone failure 2026-01-02 u1 push)"
t green red-run-of-an-absent-workflow-is-not-judged
runs_are "$(gh_run late failure 2026-01-02 u1 push)"
t red red-run-of-a-workflow-on-page-two-is-judged
runs_are "$(gh_run dman failure 2026-01-02 u1 push)"
t red red-run-of-a-manually-disabled-workflow-is-judged
runs_are "$(gh_run dinact failure 2026-01-02 u1 push)"
t red red-run-of-an-inactivity-disabled-workflow-is-judged
runs_are "$(gh_run ci failure 2026-01-02 u1 push)"
t unknown run-list-fails-is-unknown "run list"
t unknown run-list-with-empty-stdout-is-unknown "" "run list"
printf 'not json' > "$tmp/runs"
t unknown run-list-that-is-not-json-is-unknown
runs_are "$(gh_run ci failure 2026-01-02 u1 push)"
t unknown workflow-list-fails-is-unknown "api *actions/workflows*"
t unknown workflow-list-with-empty-stdout-is-unknown "" "api *actions/workflows*"
t unknown issue-create-fails-is-unknown-exit-0 "issue create"
: > "$tmp/log"
OPEN=42 PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" LOG="$tmp/log" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" >/dev/null 2>&1
if grep -q "COMMENT issue comment 42" "$tmp/log" && ! grep -q ISSUE "$tmp/log"; then echo "ok   open-issue-gets-a-comment-not-a-duplicate"
else echo "FAIL open-issue-gets-a-comment-not-a-duplicate"; bad=1; fi
exit $bad
