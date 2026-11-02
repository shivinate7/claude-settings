#!/usr/bin/env bash
# Red run with a fake `gh`. Each (workflow, event group) judges its newest run: a red group opens the
# issue, and a green run of another group never hides it. Runs of an event not in events.json, and of
# a deleted or absent workflow, are not judged. A failed read or write prints `unknown` and exits 0.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
tmp="$work/case"; mkdir -p "$tmp/bin"
# Fake gh. FAIL is a glob over "$1 $2"; a call that matches it exits 1. EMPTY is a glob too; a call
# that matches it exits 0 with no output. `run list` keeps only the --json fields it is asked for,
# as gh does; unparsable runs are echoed raw.
cat > "$tmp/bin/gh" <<'SH'
#!/usr/bin/env bash
if [ -n "${FAIL:-}" ] && [[ "$1 $2" == $FAIL ]]; then echo "gh: HTTP 500 (fake)" >&2; exit 1; fi
if [ -n "${EMPTY:-}" ] && [[ "$1 $2" == $EMPTY ]]; then exit 0; fi
case "$1 $2" in
  "run list")
    want="$(printf '%s\n' "$@" | sed -n '/^--json$/{n;p;}')"
    jq --arg want "$want" '[.[] | with_entries(select(.key as $k | $want | split(",") | any(. == $k)))]' "$RUNS" 2>/dev/null || cat "$RUNS" ;;
  api*) cat "$WORKFLOWS" ;;
  "issue list") echo "${OPEN:-}" ;;
  "issue create") echo "ISSUE $*" >> "$LOG" ;;
  "issue comment") echo "COMMENT $*" >> "$LOG" ;;
esac
SH
chmod +x "$tmp/bin/gh"
# Fixture, one home. gh_run prints one run as `gh run list --json` returns it: args are workflow,
# conclusion, createdAt, url, event. Ids: ci 1, deploy 2, alarm 3, pages 4, old 5 (deleted),
# gone 6 (absent from the list), late 7 (on page two of the workflows list), dman 8 and dinact 9
# (disabled, on page two).
gh_run() {
  local id
  case "$1" in ci) id=1 ;; deploy) id=2 ;; alarm) id=3 ;; pages) id=4 ;; old) id=5 ;; gone) id=6 ;; late) id=7 ;;
    dman) id=8 ;; dinact) id=9 ;; esac
  printf '{"workflowName":"%s","workflowDatabaseId":%s,"conclusion":"%s","createdAt":"%s","url":"%s","event":"%s"}\n' "$1" "$id" "$2" "$3" "$4" "$5"
}
runs_are() { printf '%s\n' "$@" | jq -s . > "$tmp/runs"; }
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
  out="$(PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" LOG="$tmp/log" FAIL="${3:-}" EMPTY="${4:-}" \
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
runs_are "$(gh_run ci success 2026-01-02 u1 push)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
t red red-schedule-is-not-cleared-by-a-newer-green-push
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
t red red-schedule-is-not-cleared-by-a-newer-green-dispatch
runs_are "$(gh_run ci success 2026-01-02 u1 schedule)" "$(gh_run ci failure 2026-01-01 u0 schedule)"
t green red-schedule-is-cleared-by-a-newer-green-schedule
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch)" "$(gh_run ci failure 2026-01-01 u0 push)"
t green red-push-is-cleared-by-a-newer-green-dispatch
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
