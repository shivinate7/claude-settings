#!/usr/bin/env bash
# Red run with a fake `gh`. Each (workflow, event group) judges its newest run: a red group opens the
# issue. A green run of another group clears it only when that run is newer, is the newest of its group,
# succeeded, and passed every job of the red run. Runs of an event not in events.json, and of a deleted
# or absent workflow, are not judged. A failed read or write prints `unknown` and exits 0.
# The revert-clear cases (a red run that a revert on the branch clears, read through search/commits and compare) come after
# the cross-group cases. The dropped-start cases (dropped.sh, the alarm for a pull request whose all-jobs-passed run never
# started) come last. They use their own fake routes and fixtures, so the cases above read nothing new.
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
# fails the read, so an unexpected read is unknown. The dropped-start routes (pulls, check runs, issue
# comments, and a POST of a comment) serve DROP_PULLS/<page>, one JSON document per page (--paginate serves
# every page, without it only page 1), DROP_CHECKS/<sha> and DROP_COMMENTS/<pr>, log each api call to
# DROP_READS and each POST to DROP_LOG, and fail a read with no fixture.
cat > "$tmp/bin/gh" <<'SH'
#!/usr/bin/env bash
# classify: what one api call is, for the reads log: pulls, checks <route>, comments <pr>, post <pr>, other.
classify() {
  local route method=GET n
  route="$(printf '%s\n' "$@" | sed -n '/^repos\//{p;q;}')"
  [ "$2" = --method ] && method="$3"
  case "$route" in
    */pulls|*/pulls\?*) echo pulls ;;
    */check-runs*) echo "checks $route" ;;
    */issues/*/comments*)
      n="${route#*issues/}"; n="${n%%/*}"
      if [ "$method" = POST ]; then echo "post $n"; else echo "comments $n"; fi ;;
    *) echo other ;;
  esac
}
# serve_pages <dir> <jq filter or ""> <paged or ""> : one list read. Each page is one JSON document in <dir>/<n>;
# page 1 alone unless --paginate. A missing page 1 fails the read.
serve_pages() {
  local dir="$1" jqf="$2" paged="$3" k=1
  [ -f "$dir/1" ] || { echo "gh: no fixture in $dir (fake)" >&2; exit 1; }
  while [ -f "$dir/$k" ]; do
    if [ -n "$jqf" ]; then jq -r "$jqf" "$dir/$k" || exit 1; else cat "$dir/$k"; fi
    [ -n "$paged" ] || break
    k=$((k + 1))
  done
  exit 0
}
# dropped_api: serves a dropped-start read from its fixture, or logs a POST with its body.
dropped_api() {
  local route body="" jqf="" prev="" paged="" a file="" sha n
  route="$(printf '%s\n' "$@" | sed -n '/^repos\//{p;q;}')"
  for a in "$@"; do
    case "$a" in body=*) body="${a#body=}" ;; esac
    if [ "$prev" = --jq ] || [ "$prev" = -q ]; then jqf="$a"; fi
    if [ "$a" = --paginate ]; then paged=1; fi
    prev="$a"
  done
  if [ "$2" = --method ]; then printf 'POST %s\n%s\n' "$route" "$body" >> "$DROP_LOG"; echo '{"id": 1}'; exit 0; fi
  case "$route" in
    */pulls|*/pulls\?*) serve_pages "$DROP_PULLS" "$jqf" "$paged" ;;
    */check-runs*) sha="${route#*commits/}"; file="$DROP_CHECKS/${sha%%/*}" ;;
    */issues/*/comments*) n="${route#*issues/}"; serve_pages "$DROP_COMMENTS/${n%%/*}" "$jqf" "$paged" ;;
  esac
  [ -f "$file" ] || { echo "gh: no fixture for $route (fake)" >&2; exit 1; }
  if [ -n "$jqf" ]; then jq -r "$jqf" "$file"; exit $?; fi
  cat "$file"
}
# contents_api "$@": one workflow file at a head, `repos/<repo>/contents/<path>` with the ref in the query or as an -f ref= field.
# Serves $CONTENTS/<ref>/<path> when that file exists, else $CONTENTS_DEFAULT, a file with one job and no if:, so a case that
# sets no file reads every job name as one that may run. Raw when an Accept header asks for raw, else the JSON reply with base64 content.
contents_api() {
  local route="$2" path ref="" file arg
  path="${route#*/contents/}"
  case "$path" in *\?ref=*) ref="${path#*\?ref=}"; path="${path%%\?*}" ;; esac
  for arg in "$@"; do case "$arg" in ref=*) ref="${arg#ref=}" ;; esac; done
  file="$CONTENTS/$ref/$path"
  [ -f "$file" ] || file="$CONTENTS_DEFAULT"
  if printf '%s\n' "$@" | grep -q 'vnd.github.raw'; then cat "$file"; else printf '{"encoding":"base64","content":"%s"}\n' "$(base64 -w0 < "$file")"; fi
  exit 0
}
# revert_api: the revert reads, dispatched on $apiroute. search/commits takes GET: `search/commits?q=...`, or
# `-X GET search/commits -f q=...` (a -f field alone makes gh send a POST, which search refuses). The query names one head
# sha, the 40-hex in the args; the read answers $REVERTS/search/<sha>, and a missing file is an empty reply, {"items": []}.
# repos/<repo>/compare/<rev>...<branch> answers $REVERTS/compare/<rev>...<branch>; a missing file fails the read. Each
# read is logged to $VREADS as `search <sha>` or `compare <rev>...<branch>`.
revert_api() {
  local key file
  case "$apiroute" in
    search/*)
      key="$(printf '%s\n' "$@" | grep -oE '[0-9a-f]{40}' | head -1)"
      echo "search $key" >> "${VREADS:-/dev/null}"
      file="${REVERTS:-/nonexistent}/search/$key"
      if [ -f "$file" ]; then cat "$file"; else echo '{"items": []}'; fi ;;
    *)
      key="${apiroute#*compare/}"; key="${key%%\?*}"
      echo "compare $key" >> "${VREADS:-/dev/null}"
      file="${REVERTS:-/nonexistent}/compare/$key"
      [ -f "$file" ] || { echo "gh: no compare fixture for $key (fake)" >&2; exit 1; }
      cat "$file" ;;
  esac
  exit 0
}
if [ "$1" = api ]; then classify "$@" >> "${DROP_READS:-/dev/null}"; fi
# The first route argument, so a flag before the route does not hide it from FAIL or from the dispatch.
apiroute="$(printf '%s\n' "$@" | sed -n '/^\(repos\/\|search\/\)/{p;q;}')"
if [ -n "${FAIL:-}" ] && { [[ "$1 $2" == $FAIL ]] || [[ "$1 $apiroute" == $FAIL ]]; }; then echo "gh: HTTP 500 (fake)" >&2; exit 1; fi
if [ -n "${EMPTY:-}" ] && [[ "$1 $2" == $EMPTY ]]; then exit 0; fi
case "$1 $2" in
  "run list")
    want="$(printf '%s\n' "$@" | sed -n '/^--json$/{n;p;}')"
    status="$(printf '%s\n' "$@" | sed -n '/^--status$/{n;p;}')"
    jq --arg want "$want" --arg status "$status" '[.[] | select($status == "" or .status == $status) | with_entries(select(.key as $k | $want | split(",") | any(. == $k)))]' "$RUNS" 2>/dev/null || cat "$RUNS" ;;
  api*)
    case "$apiroute" in search/*|repos/*/compare/*) revert_api "$@" ;; esac
    case "$2" in
      */actions/runs/*/jobs*)
        id="${2#*actions/runs/}"; id="${id%%/*}"
        echo "$2" >> "${READS:-/dev/null}"
        if [ -f "${JOBS:-/nonexistent}/$id" ]; then cat "$JOBS/$id"; else echo "gh: no jobs fixture for run $id (fake)" >&2; exit 1; fi ;;
      --method|*/pulls|*/pulls\?*|*/check-runs*|*/issues/*/comments*) dropped_api "$@" ;;
      */contents/*) contents_api "$@" ;;
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
    dman) id=8 ;; dinact) id=9 ;; links) id=10 ;; checks) id=11 ;; esac
  concl="\"$2\""; [ "$2" = null ] && concl=null
  printf '{"workflowName":"%s","workflowDatabaseId":%s,"databaseId":%s,"conclusion":%s,"createdAt":"%s","url":"%s","event":"%s","status":"%s","headSha":"%040x"}\n' \
    "$1" "$id" "$6" "$concl" "$3" "$4" "$5" "${7:-completed}" "$6"
}
# A case starts with its runs: runs_are clears the jobs and the revert fixtures of the case before, then the jobs_of and
# revert fixture lines that follow it.
runs_are() { printf '%s\n' "$@" | jq -s . > "$tmp/runs"; rm -rf "$tmp/jobs"; mkdir -p "$tmp/jobs"; rm -rf "$tmp/revert"; mkdir -p "$tmp/revert/search" "$tmp/revert/compare"; }
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
{"total_count": 10, "workflows": [
  {"id": 7, "name": "late", "path": ".github/workflows/late.yml", "state": "active"},
  {"id": 8, "name": "dman", "path": ".github/workflows/dman.yml", "state": "disabled_manually"},
  {"id": 9, "name": "dinact", "path": ".github/workflows/dinact.yml", "state": "disabled_inactivity"},
  {"id": 10, "name": "links", "path": ".github/workflows/links.yml", "state": "active"},
  {"id": 11, "name": "checks", "path": ".github/workflows/checks.yml", "state": "active"}]}
JSON
# The file a head serves when a case sets none (contents_api): one job with no if:.
cat > "$tmp/no-if.yml" <<'YML'
name: checks
on: push
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
YML
bad=0
t() { # want label [FAIL glob] [EMPTY glob] [text the issue must name, or !text it must not] [jobs reads: "none", or the run paths read, in any order] [revert reads: "none", "any", or the reads exactly, ';'-separated]
  : > "$tmp/log"; : > "$tmp/reads"; : > "$tmp/vreads"
  out="$(PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" JOBS="$tmp/jobs" READS="$tmp/reads" LOG="$tmp/log" \
    REVERTS="$tmp/revert" VREADS="$tmp/vreads" \
    FAIL="${3:-}" EMPTY="${4:-}" CONTENTS="$tmp/contents" CONTENTS_DEFAULT="$tmp/no-if.yml" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" 2>"$tmp/err")"
  code=$?
  shown="$(grep -v '^::warning::' <<<"$out")" # the verdict, without annotations
  why=""  # the first cause that fails
  if [ "$code" != 0 ]; then why="exit $code, want 0"
  elif [ "$shown" != "$1" ]; then why="verdict '$shown', want '$1'"
  elif [ "$1" = red ] && ! grep -q ISSUE "$tmp/log"; then why="no issue written"
  elif [ "$1" != red ] && [ -s "$tmp/log" ]; then why="an issue was written"
  elif [ "$1" = unknown ] && ! grep -q '::warning::' <<<"$out"$'\n'"$(cat "$tmp/err")"; then why="no ::warning:: line"
  elif [ -n "${5:-}" ]; then
    case "$5" in
      !*) grep -qF -- "${5#!}" "$tmp/log" && why="the issue names '${5#!}', which it must not" ;;
      *) grep -qF -- "$5" "$tmp/log" || why="the issue lacks '$5'" ;;
    esac
  fi
  if [ -z "$why" ] && [ -n "${6:-}" ]; then
    expect_reads="$(tr ' ' '\n' <<<"$6" | grep -v '^none$' | sort | tr '\n' ' ')"
    got_reads="$(grep -o 'actions/runs/[0-9]*/jobs' "$tmp/reads" | sort | tr '\n' ' ')"
    [ "$expect_reads" = "$got_reads" ] || why="jobs reads '$got_reads', want '$expect_reads'"
  fi
  if [ -z "$why" ] && [ -n "${7:-}" ]; then
    case "$7" in
      none) [ -s "$tmp/vreads" ] && why="revert reads '$(tr '\n' ';' < "$tmp/vreads")', want none" ;;
      any) [ -s "$tmp/vreads" ] || why="no revert read, want one" ;;
      *) [ "$(sort "$tmp/vreads")" = "$(tr ';' '\n' <<<"$7" | sort)" ] || why="revert reads '$(tr '\n' ';' < "$tmp/vreads")', want '$7'" ;;
    esac
  fi
  if [ -z "$why" ]; then echo "ok   $2"; else echo "FAIL $2: $why"; bad=1; fi
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
# A failed run's red job is cleared by a newer green run of the other group only when that run passes every job the red run needs.
# A job the red run did not fail, whose job-level if: needs pull_request (the other event), is not needed. A red job always is.
# The workflow file is read at the green run's head (headSha) through the contents route.
serve_real_checks() { mkdir -p "$tmp/contents/$1/.github/workflows" && cp "$root/.github/workflows/checks.yml" "$tmp/contents/$1/.github/workflows/checks.yml"; }
# The live nightly case: schedule run 41817705653 failed on checks-windows-merge-3, all-jobs-passed and ci-done skipped. The newer
# push run 41905916525 passed merge-3 and skipped the same two. The file is the real checks.yml, at the push run's head.
live_pair() {
  runs_are "$(gh_run checks success 2026-11-03T14:12:08Z https://runs/live-push-41905916525 push 41905916525)" \
    "$(gh_run checks failure 2026-11-02T06:00:21Z https://runs/live-schedule-41817705653 schedule 41817705653)"
  jobs_of 41817705653 checks-windows-merge-3:failure all-jobs-passed:skipped ci-done:skipped
  jobs_of 41905916525 checks-windows-merge-3:success all-jobs-passed:skipped ci-done:skipped
  serve_real_checks "$(printf '%040x' 41905916525)"
}
live_pair
t green live-nightly-red-schedule-is-cleared-by-the-newer-push-run-that-passed-its-red-job "" ""
live_pair
t unknown live-nightly-failed-read-of-the-workflow-file-is-unknown-not-clear "api *contents/*"
# A red job whose if: excludes the push event (all-jobs-passed is pull_request-only) is never dropped, so the failed schedule run alarms.
runs_are "$(gh_run checks success 2026-11-03T14:12:08Z https://runs/pr-only-push-52 push 52)" \
  "$(gh_run checks failure 2026-11-02T06:00:21Z https://runs/pr-only-schedule-51 schedule 51)"
jobs_of 51 checks-windows-merge-3:success all-jobs-passed:failure
jobs_of 52 checks-windows-merge-3:success all-jobs-passed:skipped
serve_real_checks "$(printf '%040x' 52)"
t red red-job-whose-if-excludes-the-push-event-is-never-dropped "" "" https://runs/pr-only-schedule-51
# A certain red needs no workflow file: a red job the newer green run lacks, or did not pass, alarms even when the contents read fails.
runs_are "$(gh_run checks success 2026-11-03T14:12:08Z https://runs/absent-push-61 push 61)" \
  "$(gh_run checks failure 2026-11-02T06:00:21Z https://runs/absent-schedule-60 schedule 60)"
jobs_of 60 checks-windows-merge-3:failure all-jobs-passed:skipped
jobs_of 61 all-jobs-passed:skipped
t red red-job-missing-from-the-newer-run-is-red-when-the-workflow-read-fails "api *contents/*" "" https://runs/absent-schedule-60
runs_are "$(gh_run checks success 2026-11-03T14:12:08Z https://runs/skipped-push-63 push 63)" \
  "$(gh_run checks failure 2026-11-02T06:00:21Z https://runs/skipped-schedule-62 schedule 62)"
jobs_of 62 checks-windows-merge-3:failure all-jobs-passed:skipped
jobs_of 63 checks-windows-merge-3:skipped all-jobs-passed:skipped
t red red-job-skipped-in-the-newer-run-is-red-when-the-workflow-read-fails "api *contents/*" "" https://runs/skipped-schedule-62

# --- revert clear: a red run that a revert on the branch clears (merge/merge.py, the revert clear) ---
# The alarm has no checkout, so it reads reverts through the API. Per red run head: one search/commits read, filtered
# client-side to the 40-hex `This reverts commit <head>` line. Per link: one compare read, `repos/o/r/compare/<rev>...main`;
# status ahead or identical means reachable, diverged or behind does not. A revert of a revert is followed the same way:
# an odd chain clears, an even chain does not. The fixtures are files: $tmp/revert/search/<head> is the search reply, and
# $tmp/revert/compare/<rev>...main is the compare reply. runs_are empties both for each case.
H1=$(printf '%040x' 1); H2=$(printf '%040x' 2)                                          # the heads of runs 1 and 2 (gh_run's headSha)
V1=aaaa$(printf '%036x' 1); V2=bbbb$(printf '%036x' 2); V3=cccc$(printf '%036x' 3)      # revert commits
D1="${H1:0:20}f${H1:21}"                                                                 # head 1 with one digit off, in the middle
SHORT="${H1:0:7}"                                                                        # the first 7 digits of head 1
# hit <sha> <message>: one search/commits hit, {"sha": ..., "commit": {"message": ...}}.
hit() { jq -cn --arg s "$1" --arg m "$2" '{sha: $s, commit: {message: $m}}'; }
# reverts <sha>: the message of a commit that reverts <sha>, as git writes it.
reverts() { printf 'Revert "change"\n\nThis reverts commit %s.\n' "$1"; }
# search_is <head> [hit]...: the search reply for one head, {"items": [...]}; with no hit, an empty list.
search_is() { local h="$1"; shift; printf '%s\n' "$@" | jq -s '{items: .}' > "$tmp/revert/search/$h"; }
# cmp_is <rev> <status>: the compare reply for <rev>...main.
cmp_is() { printf '{"status": "%s"}\n' "$2" > "$tmp/revert/compare/$1...main"; }
# red_jobs <run id>...: one failed job for each red run, so a jobs read never fails here. The alarm judges a red run without them.
red_jobs() { local i; for i in "$@"; do jobs_of "$i" checks:failure; done; }
# Scope first: the red run with no revert alarms, so a green below is a clear and not a run the alarm never judged.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1"
t red revert-control-no-revert-still-alarms "" "" https://runs/red-1
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; cmp_is "$V1" ahead
t green revert-on-the-branch-clears-the-red-run
for st in ahead identical; do
  runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
  search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; cmp_is "$V1" "$st"
  t green "revert-reachable-by-status-$st-clears-the-red-run"
done
for st in diverged behind; do
  runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
  search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; cmp_is "$V1" "$st"
  t red "revert-not-reachable-by-status-$st-does-not-clear" "" "" https://runs/red-1
done
# The search reply is filtered client-side: a sha one digit off, a short sha, the red run's own commit, and a hit that names
# the head without the revert line all leave the red run red. Each decoy's compare is `ahead`, so a loose filter would clear it.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$D1")")"; cmp_is "$V1" ahead
t red revert-naming-a-head-one-digit-off-does-not-clear "" "" https://runs/red-1
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$SHORT")")"; cmp_is "$V1" ahead
t red revert-naming-a-short-sha-does-not-clear "" "" https://runs/red-1
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$H1" "$(reverts "$H1")")"; cmp_is "$H1" ahead
t red the-red-run-own-commit-is-not-its-revert "" "" https://runs/red-1
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "Fix the change that $H1 made")"; cmp_is "$V1" ahead
t red a-hit-that-names-the-head-without-the-revert-line-does-not-clear "" "" https://runs/red-1
# A full page of other hits: the revert is the last of 31 items in one reply, and it still clears.
decoys=(); for i in $(seq 1 30); do decoys+=("$(hit "$(printf '%040x' $((1000 + i)))" "unrelated change $i")"); done
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "${decoys[@]}" "$(hit "$V1" "$(reverts "$H1")")"; cmp_is "$V1" ahead
t green revert-after-a-full-page-of-other-hits-clears-the-red-run
# Chains: an even chain leaves the red run red, an odd chain clears it, and a revert of a revert not on the branch does not count.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; search_is "$V1" "$(hit "$V2" "$(reverts "$V1")")"; search_is "$V2"
cmp_is "$V1" ahead; cmp_is "$V2" ahead
t red revert-of-a-revert-is-an-even-chain-and-leaves-the-red-run-red "" "" https://runs/red-1
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; search_is "$V1" "$(hit "$V2" "$(reverts "$V1")")"
search_is "$V2" "$(hit "$V3" "$(reverts "$V2")")"; search_is "$V3"
cmp_is "$V1" ahead; cmp_is "$V2" ahead; cmp_is "$V3" ahead
t green revert-of-a-revert-of-a-revert-is-an-odd-chain-and-clears-the-red-run
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; search_is "$V1" "$(hit "$V2" "$(reverts "$V1")")"; search_is "$V2"
cmp_is "$V1" ahead; cmp_is "$V2" diverged
t green revert-of-a-revert-not-on-the-branch-does-not-undo-the-clear
# Two red runs in two workflows, each judged. The revert of the newer one clears only that one.
runs_are "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)" "$(gh_run deploy failure 2026-01-02 https://runs/red-2 push 2)"
red_jobs 1 2
search_is "$H1"; search_is "$H2" "$(hit "$V2" "$(reverts "$H2")")"; cmp_is "$V2" ahead
t red revert-of-the-newer-run-leaves-the-older-red-run-red "" "" https://runs/red-1
t red revert-of-the-newer-run-does-not-name-the-run-it-clears "" "" "!https://runs/red-2"
# A read that fails or gives a malformed reply is unknown: never green, and no issue.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
t unknown revert-search-fails-is-unknown-and-opens-no-issue "api *search/commits*"
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"
t unknown revert-compare-fails-is-unknown-and-opens-no-issue "api *compare/*"
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
printf 'not json' > "$tmp/revert/search/$H1"
t unknown revert-search-reply-that-is-not-json-is-unknown-and-opens-no-issue
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; printf '{}\n' > "$tmp/revert/compare/$V1...main"
t unknown revert-compare-reply-with-no-status-is-unknown-and-opens-no-issue
# A hit whose commit is a string: its message cannot be read, so the read is unknown. An uncaught exception would exit 1, which
# alarm.sh reads as no revert and alarms red.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)"; red_jobs 1
search_is "$H1" "{\"sha\": \"$V1\", \"commit\": \"Revert of the head\"}"
t unknown revert-search-hit-whose-commit-is-a-string-is-unknown-and-opens-no-issue
# Cost: revert reads only for a red run. None when every run is green, a cancelled run is the only failure, or a re-run is in flight.
runs_are "$(gh_run ci success 2026-01-02 u1 push 1)" "$(gh_run deploy success 2026-01-01 u0 push 2)"
t green cost-all-green-makes-no-revert-read "" "" "" "" none
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cancelled-1 push 1)"
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; cmp_is "$V1" ahead
t green cost-cancelled-run-makes-no-revert-read "" "" "" "" none
runs_are "$(gh_run ci null 2026-01-02 https://runs/rerun-1 push 1 in_progress)"
search_is "$H1" "$(hit "$V1" "$(reverts "$H1")")"; cmp_is "$V1" ahead
t green cost-re-run-in-flight-makes-no-revert-read "" "" "" "" none
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure scope:success
jobs_of 2 checks:success scope:success
t green cost-red-run-cleared-across-groups-makes-no-revert-read "" "" "" "" none
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)" "$(gh_run deploy success 2026-01-03 https://runs/green-2 push 2)"; red_jobs 1
t red cost-one-red-run-reads-one-search-for-its-own-head "" "" https://runs/red-1 "" "search $H1"

# --- dropped-start: dropped.sh alarms on a pull request whose all-jobs-passed run never started ---
# A case builds its fixtures under $dd, then drun runs dropped.sh once: CHECK unset, NOW given, fake gh.
dropped="$here/dropped.sh"
DNOW=1800000000                       # 2027-01-15T08:00:00Z, given so no case reads the real clock
OLD=2027-01-15T07:50:00Z              # 600 s before DNOW: old enough to flag
AT300=2027-01-15T07:55:00Z            # 300 s before: on the line, not flagged
AT301=2027-01-15T07:54:59Z            # 301 s before: just past the line, flagged
SHA_A=0123456789abcdef0123456789abcdef01234567
SHA_B=fedcba9876543210fedcba9876543210fedcba98
dd="$tmp/dropped"
# dnew: an empty fixture folder for one case.
dnew() { rm -rf "$dd"; mkdir -p "$dd/checks" "$dd/comments"; : > "$dd/pulls.lines"; }
# dpr <number> <head sha> <updated_at> [draft]: one open pull request, as the pulls list gives it.
dpr() {
  jq -cn --argjson n "$1" --arg sha "$2" --arg u "$3" --argjson d "${4:-false}" \
    '{number: $n, draft: $d, updated_at: $u, head: {sha: $sha, ref: ("branch-" + ($n | tostring))}}' >> "$dd/pulls.lines"
}
# dpage: the pull requests after this line are on the next page of the pulls list.
dpage() { echo PAGE >> "$dd/pulls.lines"; }
# dchecks <sha> <json array>: the check runs of one head commit, as the check-runs read gives them.
dchecks() { jq -n --argjson r "$2" '{total_count: ($r | length), check_runs: $r}' > "$dd/checks/$1"; }
# dcomments <pr> [body]: page 1 of the comments of one PR; a PR given no body has none.
dcomments() {
  mkdir -p "$dd/comments/$1"
  if [ $# -lt 2 ]; then echo '[]'; else jq -cn --arg b "$2" '[{id: 1, body: $b}]'; fi > "$dd/comments/$1/1"
}
# dcommentpage <pr> <page> <body>: a later page of the comments of one PR, holding one comment.
dcommentpage() { jq -cn --arg b "$3" '[{id: 2, body: $b}]' > "$dd/comments/$1/$2"; }
# drun <FAIL glob or "">: one run of dropped.sh on $dd. Sets out, code, and the reads and log files.
drun() {
  rm -rf "$dd/pulls"; mkdir -p "$dd/pulls"
  n=1; : > "$dd/page.lines"
  while IFS= read -r ln; do
    if [ "$ln" = PAGE ]; then jq -s . "$dd/page.lines" > "$dd/pulls/$n"; n=$((n + 1)); : > "$dd/page.lines"
    else printf '%s\n' "$ln" >> "$dd/page.lines"; fi
  done < "$dd/pulls.lines"
  jq -s . "$dd/page.lines" > "$dd/pulls/$n"
  : > "$dd/reads"; : > "$dd/log"
  out="$(env -u CHECK PATH="$tmp/bin:$PATH" DROP_PULLS="$dd/pulls" DROP_CHECKS="$dd/checks" DROP_COMMENTS="$dd/comments" \
    DROP_READS="$dd/reads" DROP_LOG="$dd/log" FAIL="$1" GH_TOKEN=x GITHUB_REPOSITORY=o/r NOW="$DNOW" \
    bash "$dropped" 2>"$dd/err")"
  code=$?
}
# countok <expected> <got>: the expected count, or `*` for any count.
countok() { [ "$1" = '*' ] || [ "$1" = "$2" ]; }
# td <verdict> <label> <FAIL glob or ""> <pulls> <check reads> <comment reads> <POST attempts> [text]...
# Runs drun and names the first cause that fails: exit code, verdict, the ::warning:: line of unknown, the api
# reads per route (`*` is any count), a read outside the routes, then each text, which must be in the log of
# POST lines and bodies. A text with a leading `!` must not be there; `re:` makes the rest an extended regex.
td() {
  local want="$1" label="$2" fail="$3" ep="$4" ek="$5" ec="$6" ew="$7" got gp gk gc gw why="" m shown
  shift 7
  drun "$fail"
  shown="$(grep -v '^::warning::' <<<"$out")"
  got="$(grep -c '^pulls' "$dd/reads") $(grep -c '^checks' "$dd/reads") $(grep -c '^comments' "$dd/reads") $(grep -c '^post' "$dd/reads")"
  read -r gp gk gc gw <<<"$got"
  if [ "$code" != 0 ]; then why="exit $code, want 0"
  elif [ "$shown" != "$want" ]; then why="verdict '$shown', want '$want'"
  elif [ "$want" = unknown ] && ! grep -q '::warning::' <<<"$out"$'\n'"$(cat "$dd/err")"; then why="no ::warning:: line"
  elif ! countok "$ep" "$gp" || ! countok "$ek" "$gk" || ! countok "$ec" "$gc" || ! countok "$ew" "$gw"; then
    why="api reads pulls/checks/comments/posts $got, want $ep/$ek/$ec/$ew"
  elif grep -q '^other' "$dd/reads"; then why="an api read outside the routes"
  else
    for m in "$@"; do
      case "$m" in
        !*) if grep -qF -- "${m#!}" "$dd/log"; then why="log holds '${m#!}'"; break; fi ;;
        re:*) if ! grep -qE -- "${m#re:}" "$dd/log"; then why="log lacks /${m#re:}/"; break; fi ;;
        *) if ! grep -qF -- "$m" "$dd/log"; then why="log lacks '$m'"; break; fi ;;
      esac
    done
  fi
  if [ -z "$why" ]; then echo "ok   $label"; else echo "FAIL $label: $why"; bad=1; fi
}

dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'; dcomments 1
td red dropped-old-pr-without-check-run-is-red "" '*' '*' '*' '*' "POST repos/o/r/issues/1/comments" "<!-- dropped-start-alarm:$SHA_A -->"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'; dcomments 1
td red dropped-one-flagged-pr-reads-each-route-once "" 1 1 1 1 "POST repos/o/r/issues/1/comments"
dnew; dpr 1 "$SHA_A" "$OLD" true
td green dropped-draft-pr-is-green-with-no-check-read "" 1 0 0 0 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$AT300"
td green dropped-update-300s-old-is-green "" 1 0 0 0 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$AT301"; dchecks "$SHA_A" '[]'; dcomments 1
td red dropped-update-301s-old-is-red "" 1 1 1 1 "POST repos/o/r/issues/1/comments"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[{"name":"all-jobs-passed","conclusion":"skipped"}]'; dcomments 1
td red dropped-skipped-only-run-counts-as-absent "" 1 1 1 1 "POST repos/o/r/issues/1/comments"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[{"name":"all-jobs-passed","conclusion":"success"}]'
td green dropped-success-run-is-green-with-no-comment "" 1 1 0 0 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'
dcomments 1 "<!-- dropped-start-alarm:$SHA_A -->
already flagged"
td green dropped-marker-for-this-head-is-green-with-no-new-comment "" 1 1 1 0 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'
dcomments 1 "<!-- dropped-start-alarm:$SHA_B -->
an older head"
td red dropped-marker-for-another-head-does-not-suppress "" 1 1 1 1 "POST repos/o/r/issues/1/comments" "<!-- dropped-start-alarm:$SHA_A -->"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'; dcomments 1
td unknown dropped-check-run-read-fails-is-unknown-with-no-comment "api *check-runs*" 1 1 0 0 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$OLD"; dpr 2 "$SHA_B" "$OLD"; dchecks "$SHA_A" '[]'; dchecks "$SHA_B" '[]'; dcomments 1; dcomments 2
td unknown dropped-comment-write-fails-is-unknown-and-stops "api --method*" 1 '*' '*' 1 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[{"name":"all-jobs-passed","conclusion":"success"}]'
drun ""
# The default is compared with the constant itself (hooks/required_check.py, the one home), never a string match.
want_check="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); from required_check import REQUIRED_CHECK; print(REQUIRED_CHECK)' "$root/hooks")" || want_check=""
got_check="$(sed -n 's/^checks .*check_name=\([^&]*\).*/\1/p' "$dd/reads")"
if [ -n "$want_check" ] && [ "$got_check" = "$want_check" ]; then echo "ok   dropped-check-default-is-draft-skip-check"
else echo "FAIL dropped-check-default-is-draft-skip-check: default '$got_check', want REQUIRED_CHECK '$want_check'"; bad=1; fi
# merge.DRAFT_SKIP_CHECK is the same constant. Importing merge only reads lint/layout.json; its bytecode cache is git-ignored.
merge_check="$(python3 -I -c 'import sys; sys.path[:0] = [sys.argv[1], sys.argv[2]]; import merge; print(merge.DRAFT_SKIP_CHECK)' "$root/merge" "$root/hooks")" || merge_check=""
if [ -n "$merge_check" ] && [ "$merge_check" = "$want_check" ]; then echo "ok   dropped-check-merge-draft-skip-check-is-required"
else echo "FAIL dropped-check-merge-draft-skip-check-is-required: merge.DRAFT_SKIP_CHECK '$merge_check', want REQUIRED_CHECK '$want_check'"; bad=1; fi
cause="$(python3 -I - "$here/action.yml" <<'PY'
import re, sys
lines = open(sys.argv[1], encoding="utf-8").read().split("\n")

def under(lines, head, indent):
    # The lines under `head`, up to the next non-blank line at `indent` or less.
    out, on = [], False
    for ln in lines:
        if not on:
            on = ln.startswith(head)
            continue
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            break
        out.append(ln)
    return out

ds = under(under(lines, "inputs:", 0), "  dropped-start:", 2)
steps = []
for ln in under(under(lines, "runs:", 0), "  steps:", 2):
    if ln.startswith("    - "):
        steps.append([ln])
    elif steps and ln.strip():
        steps[-1].append(ln)
alarm = [s for s in steps if s[0].strip() == "- name: Alarm on a red branch"]
dropped_steps = [s for s in steps if any("dropped.sh" in ln for ln in s)]
defaults = [m.group(1).strip("'\"") for m in (re.match(r"^    default:\s*(.*?)\s*$", ln) for ln in ds) if m]
ifs = [ln for ln in dropped_steps[0] if re.match(r"^      if:", ln)] if dropped_steps else []
if not ds: cause = "no dropped-start input under inputs"
elif defaults != ["false"]: cause = "dropped-start default is %r, want 'false'" % (defaults,)
elif not alarm: cause = "no alarm step"
elif any(re.match(r"^      if:", ln) for ln in alarm[0]): cause = "the alarm step has an if; it must run alone"
elif not dropped_steps: cause = "no step runs dropped.sh"
elif not ifs: cause = "the dropped step has no if"
elif not re.search(r"inputs\.dropped-start\s*==\s*'true'", ifs[0]): cause = "the dropped step's if does not test dropped-start == 'true'"
else: cause = "ok"
print(cause)
PY
)" || cause="python could not read action.yml"
if [ "$cause" = ok ]; then echo "ok   action-yml-dropped-start-defaults-false-and-gates-only-its-step"
else echo "FAIL action-yml-dropped-start-defaults-false-and-gates-only-its-step: $cause"; bad=1; fi
dnew
td green dropped-no-open-pull-requests-is-green "" 1 0 0 0
dnew
for i in $(seq 1 100); do
  printf -v sha '%040x' "$i"
  dpr "$i" "$sha" "$OLD"
  if [ "$i" -lt 100 ]; then dchecks "$sha" '[{"name":"all-jobs-passed","conclusion":"success"}]'
  else dchecks "$sha" '[]'; dcomments "$i"; fi
done
td red dropped-full-page-of-100-flags-only-the-last "" 1 100 1 1 "POST repos/o/r/issues/100/comments"
dnew; dpr 1 "$SHA_A" "$OLD"
td unknown dropped-pulls-read-fails-is-unknown "api *pulls*" 1 0 0 0 "!POST repos/"
dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'; dcomments 1
td unknown dropped-comments-read-fails-is-unknown-with-no-post "api *issues/*/comments*" 1 1 1 0 "!POST repos/"

dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'; dcomments 1
td red dropped-comment-remedy-is-ready-and-undo-not-a-workflow-run "" 1 1 1 1 "POST repos/o/r/issues/1/comments" "gh pr ready 1 --undo" 're:gh pr ready 1([^0-9 ]|$)' "!gh workflow run"
dnew; dpr 1 "$SHA_A" "$OLD"; dpage; dpr 2 "$SHA_B" "$OLD"
dchecks "$SHA_A" '[{"name":"all-jobs-passed","conclusion":"success"}]'; dchecks "$SHA_B" '[]'; dcomments 2
td red dropped-flagged-pr-on-page-two-is-found-from-one-pulls-read "" 1 2 1 1 "POST repos/o/r/issues/2/comments"

dnew; dpr 1 "$SHA_A" "$OLD"; dchecks "$SHA_A" '[]'; dcomments 1 "an unrelated comment"
dcommentpage 1 2 "<!-- dropped-start-alarm:$SHA_A -->
already flagged"
td green dropped-marker-on-page-two-of-comments-is-green-with-no-post "" 1 1 1 0 "!POST repos/"

exit $bad
