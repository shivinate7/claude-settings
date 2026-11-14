#!/usr/bin/env bash
# Red run with a fake `gh`. Each (workflow, event group) judges its newest run: a red group opens the
# issue. A green run of another group clears it only when that run is newer, is the newest of its group,
# succeeded, and passed every job of the red run. Runs of an event not in events.json, and of a deleted
# or absent workflow, are not judged. A failed read or write prints `unknown` and exits 0.
# A cap end wakes the merged pull request once per cap-end run and attempt, through wake.sh. A cap end with no red run opens no
# issue, and a red issue names no cap end.
# The dropped-start cases (dropped.sh, the alarm for a pull request whose all-jobs-passed run never started)
# come last. They use their own fake routes and fixtures, so the cases above read nothing new.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
tmp="$work/case"; mkdir -p "$tmp/bin"
# A python3 that logs each start to PYLOG, then runs the real one. The cost check counts the interpreter starts of a run.
real_py="$(command -v python3)"
printf '#!/usr/bin/env bash\necho python3 >> "${PYLOG:-/dev/null}"\nexec %q "$@"\n' "$real_py" > "$tmp/bin/python3"
chmod +x "$tmp/bin/python3"
# Fake gh. FAIL is a glob over "$1 $2"; a call that matches it exits 1. EMPTY is a glob too; a call
# that matches it exits 0 with no output. `run list` keeps only the --json fields it is asked for and
# the runs of the --status it is asked for, as gh does; unparsable runs are echoed raw. `api` routes
# the jobs of a run to $JOBS/<run id>, and the jobs of an earlier attempt (attempts/<n>/jobs) to $JOBS/<run id>.a<n>;
# every api call is logged in $READS. A run with no jobs fixture
# fails the read, so an unexpected read is unknown. The dropped-start routes (pulls, check runs, issue
# comments, and a POST of a comment) serve DROP_PULLS/<page>, one JSON document per page (--paginate serves
# every page, without it only page 1), DROP_CHECKS/<sha> and DROP_COMMENTS/<pr>, log each api call to
# DROP_READS and each POST to DROP_LOG, and fail a read with no fixture. The wake's reads (wake.sh) serve
# WAKE_PULLS/<sha>, the pulls of a head commit, and DROP_COMMENTS/<pr>, the comments of a pull request; its
# `gh pr comment` is logged to WAKE_LOG and its body to WAKE_BODIES; every `gh issue` call goes to ISSUE_CALLS.
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
# wake_pulls <route> <api args>: the pulls read of one head commit, served from WAKE_PULLS/<sha> as one JSON document.
# The read is logged to WAKE_LOG. A commit with no fixture fails the read.
wake_pulls() {
  local sha="${1#*/commits/}" jqf="" prev="" a
  sha="${sha%%/*}"; shift
  for a in "$@"; do if [ "$prev" = --jq ] || [ "$prev" = -q ]; then jqf="$a"; fi; prev="$a"; done
  echo "pulls $sha" >> "${WAKE_LOG:-/dev/null}"
  [ -f "$WAKE_PULLS/$sha" ] || { echo "gh: no pulls fixture for $sha (fake)" >&2; exit 1; }
  if [ -n "$jqf" ]; then jq -r "$jqf" "$WAKE_PULLS/$sha" || exit 1; else cat "$WAKE_PULLS/$sha"; fi
  exit 0
}
# wake_comments <route> <api args>: the comments read of a pull request, served as dropped_api serves it (every page with
# --paginate), and logged to WAKE_LOG.
wake_comments() {
  local n="${1#*issues/}"
  n="${n%%/*}"; echo "comments $n" >> "${WAKE_LOG:-/dev/null}"
  dropped_api "${@:2}"
}
# wake_post <gh pr comment args>: one `gh pr comment` of the wake. Logged to WAKE_LOG as `post <pr> <repo>`, its body
# appended to WAKE_BODIES.
wake_post() {
  local pr="$3" repo="" body="" prev="" a
  for a in "$@"; do
    case "$prev" in --repo) repo="$a" ;; --body) body="$a" ;; esac
    prev="$a"
  done
  echo "post $pr $repo" >> "${WAKE_LOG:-/dev/null}"
  printf '%s\n' "$body" >> "${WAKE_BODIES:-/dev/null}"
  exit 0
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
if [ "$1" = api ]; then classify "$@" >> "${DROP_READS:-/dev/null}"; fi
# The reads log names the call's repos route, so a read that puts a flag before it (the wake's --paginate) is named too.
wroute="$(printf '%s\n' "$@" | sed -n '/^repos\//{p;q;}')"
if [ "$1" = api ]; then echo "$wroute" >> "${READS:-/dev/null}"; fi
if [ "$1" = issue ]; then echo "$*" >> "${ISSUE_CALLS:-/dev/null}"; fi
if [ "$1 $2" = "pr comment" ]; then wake_post "$@"; fi
if [ -n "${FAIL:-}" ] && [[ "$1 $2" == $FAIL ]]; then echo "gh: HTTP 500 (fake)" >&2; exit 1; fi
if [ -n "${EMPTY:-}" ] && [[ "$1 $2" == $EMPTY ]]; then exit 0; fi
case "$1 $2" in
  "run list")
    want="$(printf '%s\n' "$@" | sed -n '/^--json$/{n;p;}')"
    status="$(printf '%s\n' "$@" | sed -n '/^--status$/{n;p;}')"
    jq --arg want "$want" --arg status "$status" '[.[] | select($status == "" or .status == $status) | with_entries(select(.key as $k | $want | split(",") | any(. == $k)))]' "$RUNS" 2>/dev/null || cat "$RUNS" ;;
  api*)
    case "$wroute" in
      */commits/*/pulls*) wake_pulls "$wroute" "$@" ;;
      */issues/*/comments*) wake_comments "$wroute" "$@" ;;
    esac
    case "$2" in
      */actions/runs/*/attempts/*/jobs*)
        id="${2#*actions/runs/}"; id="${id%%/attempts/*}"; att="${2#*/attempts/}"; att="${att%%/*}"
        if [ -f "${JOBS:-/nonexistent}/$id.a$att" ]; then cat "$JOBS/$id.a$att"; else echo "gh: no attempt fixture for run $id attempt $att (fake)" >&2; exit 1; fi ;;
      */actions/runs/*/jobs*)
        id="${2#*actions/runs/}"; id="${id%%/*}"
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
# (disabled, on page two), links 10 (on page two). The attempt (8th arg) is the run's attempt number, 1 unless given.
gh_run() {
  local id concl
  case "$1" in ci) id=1 ;; deploy) id=2 ;; alarm) id=3 ;; pages) id=4 ;; old) id=5 ;; gone) id=6 ;; late) id=7 ;;
    dman) id=8 ;; dinact) id=9 ;; links) id=10 ;; checks) id=11 ;; esac
  concl="\"$2\""; [ "$2" = null ] && concl=null
  printf '{"workflowName":"%s","workflowDatabaseId":%s,"databaseId":%s,"conclusion":%s,"createdAt":"%s","url":"%s","event":"%s","status":"%s","headSha":"%040x","attempt":%s}\n' \
    "$1" "$id" "$6" "$concl" "$3" "$4" "$5" "${7:-completed}" "$6" "${8:-1}"
}
# A case starts with its runs: runs_are clears the jobs of the case before the jobs_of lines that follow it.
# The wake's fixtures (wake.sh, run by the alarm for each cap end). Each run's head commit serves DEF_PULLS, PR 7 merged into
# main, and PR 7 holds no comments. A case overrides only what it tests (wake_pulls_for, wake_comments_on).
DEF_PULLS='[{"number": 7, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "main"}}]'
# runs_are clears the jobs and the wake fixtures of the case, then sets its runs; the jobs_of lines that follow fill the jobs.
runs_are() {
  printf '%s\n' "$@" | jq -s . > "$tmp/runs"; rm -rf "$tmp/jobs"; mkdir -p "$tmp/jobs"
  rm -rf "$tmp/wake"; mkdir -p "$tmp/wake/pulls" "$tmp/wake/comments/7"; printf '[]\n' > "$tmp/wake/comments/7/1"
  for sha in $(jq -r '.[].headSha' "$tmp/runs"); do printf '%s\n' "$DEF_PULLS" > "$tmp/wake/pulls/$sha"; done
}
# wake_pulls_for <run id> <json>: the pulls of that run's head commit, as the commit's pulls read gives them.
wake_pulls_for() { printf '%s\n' "$2" > "$tmp/wake/pulls/$(printf '%040x' "$1")"; }
# wake_comments_on <pr> <json page>...: the comments of one pull request, one JSON array per page.
wake_comments_on() {
  local pr="$1" k=1 page; shift
  mkdir -p "$tmp/wake/comments/$pr"
  for page in "$@"; do printf '%s\n' "$page" > "$tmp/wake/comments/$pr/$k"; k=$((k + 1)); done
}
# jobs_of <run id> [job:conclusion[:minutes|never]]...: the jobs of one run as `gh api .../actions/runs/<id>/jobs` lists them.
# minutes: the job ran that long from 2026-01-02T10:00:00Z. never: started_at is null. No third field: no times.
jobs_of() {
  local id="$1"; shift
  printf '%s\n' "$@" | jq -Rs '
    def at($m): ("2026-01-02T10:00:00Z" | fromdateiso8601) + ($m | tonumber) * 60 | todateiso8601;
    split("\n") | map(select(length > 0) | split(":") as $f
      | {name: $f[0], status: "completed", conclusion: $f[1]}
        + (if ($f[2] // "") == "" then {}
           elif $f[2] == "never" then {started_at: null, completed_at: "2026-01-02T10:05:00Z"}
           else {started_at: "2026-01-02T10:00:00Z", completed_at: at($f[2])} end))
    | {total_count: length, jobs: .}' > "$tmp/jobs/$id"
}
# attempt_jobs_of <run id> <attempt> [job:conclusion[:minutes|never]]...: the jobs of an earlier attempt of a run, as its
# attempts/<n>/jobs read gives them. The latest attempt's jobs are jobs_of.
attempt_jobs_of() { local id="$1" att="$2"; shift 2; jobs_of "$id.a$att" "$@"; }
# workflow_file <run id> [file name]: the file served at that run's head, read from stdin. Default ci.yml under .github/workflows.
workflow_file() {
  local dir
  dir="$tmp/contents/$(printf '%040x' "$1")/.github/workflows"
  mkdir -p "$dir" && cat > "$dir/${2:-ci}.yml"
}
# workflow_at <run id> <job[:cap]>...: a ci workflow with one job per argument. A job with no cap has no timeout-minutes line.
workflow_at() {
  local id="$1" spec job cap
  shift
  {
    echo "name: ci"; echo "on: push"; echo "jobs:"
    for spec in "$@"; do
      job="${spec%%:*}"; cap=""; [ "$spec" = "$job" ] || cap="${spec#*:}"
      echo "  $job:"; echo "    runs-on: ubuntu-latest"
      [ -n "$cap" ] && echo "    timeout-minutes: $cap"
      echo "    steps:"; echo "      - run: echo ok"
    done
  } | workflow_file "$id"
}
# job_cap <job>: the job-level timeout-minutes of that job in the repo's checks.yml, comment removed. Read from the file, never copied.
job_cap() {
  awk -v j="$1" '
    $0 ~ ("^  " j ":[ \t]*$") { f = 1; next }
    /^  [A-Za-z0-9_-]+:[ \t]*$/ { f = 0 }
    f && /^    timeout-minutes:/ { sub(/^    timeout-minutes:[ \t]*/, ""); sub(/[ \t]*#.*$/, ""); print; exit }' "$root/.github/workflows/checks.yml"
}
# cost <label> <jobs reads> <contents reads> <python3 starts> [cap-end runs woken]: what the last t case did. The api reads that
# are neither jobs nor contents are the workflows list and, per woken cap-end run, one pulls read and one comments read of
# its pull request; each woken run posts once. No file is left in its TMPDIR, so a cache it made is gone. Every alarm that reaches
# the empty-run walk starts python3 once for the rule-events list. Each green push run the walk reads adds one jobs read and one
# python3 start (clear_rule.py --empty-run).
cost() {
  local total j c p other left pulls comments posts w="${5:-0}"
  total="$(wc -l < "$tmp/reads")"
  j="$(grep -c 'actions/runs/[0-9]*/jobs' "$tmp/reads")"
  c="$(grep -c '/contents/' "$tmp/reads")"
  pulls="$(grep -c '/commits/[^/]*/pulls$' "$tmp/reads")"
  comments="$(grep -c '/issues/[0-9]*/comments' "$tmp/reads")"
  other=$((total - j - c - pulls - comments))
  posts="$(grep -c '^post ' "$tmp/wakelog")"
  p="$(grep -c python3 "$tmp/pylog")"
  left="$(ls -A "$tmp/scratch")"
  if [ "$j" = "$2" ] && [ "$c" = "$3" ] && [ "$other" = 1 ] && [ "$pulls" = "$w" ] && [ "$comments" = "$w" ] && [ "$posts" = "$w" ] \
    && [ "$p" = "$4" ] && [ -z "$left" ]; then echo "ok   $1"
  else echo "FAIL $1 (jobs reads $j want $2; contents reads $c want $3; other api reads $other want 1; wake pulls $pulls, comments $comments, posts $posts want $w; python3 starts $p want $4; files left: $left)"; bad=1; fi
}
# count_is <label> <pattern> <count>: the reads in the call log of the last case run that contain <pattern>. Used where cost cannot
# count a read (an earlier attempt's jobs, which cost counts as other).
count_is() {
  local got
  got="$(grep -cF -- "$2" "$tmp/reads")"
  if [ "$got" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: $got reads of $2, want $3"; bad=1; fi
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
# run_alarm [FAIL glob] [EMPTY glob] [step summary file]: one run of alarm.sh on the case's fixtures, with a clean log, reads, wake
# log and scratch folder. The step summary is where wake.sh writes a refusal; empty, the refusal goes to stderr instead.
# Sets out (stdout), code (exit status); stderr is in $tmp/err. The one home of the run step (t and named call it).
run_alarm() {
  : > "$tmp/log"; : > "$tmp/reads"; : > "$tmp/pylog"; rm -rf "$tmp/scratch"; mkdir -p "$tmp/scratch"
  : > "$tmp/issuecalls"; : > "$tmp/wakelog"; : > "$tmp/wakebodies"; : > "$tmp/summary"
  out="$(PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" WORKFLOWS="$tmp/workflows" JOBS="$tmp/jobs" READS="$tmp/reads" LOG="$tmp/log" \
    ISSUE_CALLS="$tmp/issuecalls" WAKE_LOG="$tmp/wakelog" WAKE_BODIES="$tmp/wakebodies" WAKE_PULLS="$tmp/wake/pulls" \
    DROP_COMMENTS="$tmp/wake/comments" GITHUB_STEP_SUMMARY="${3:-}" \
    FAIL="${1:-}" EMPTY="${2:-}" PYLOG="$tmp/pylog" TMPDIR="$tmp/scratch" CONTENTS="$tmp/contents" CONTENTS_DEFAULT="$tmp/no-if.yml" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" 2>"$tmp/err")"
  code=$?
}
# wake_n <kind>: how many lines of the wake log start with <kind>: pulls, comments or post.
wake_n() { grep -c "^$1" "$tmp/wakelog"; }
# alarm_body: the first posted body opens with the marker line, then the title line. The wake's TEXT opens with the title.
alarm_body() {
  sed -n '1p' "$tmp/wakebodies" | grep -qxE '<!-- main-alarm:cap:[0-9]+:[0-9]+ -->' &&
  sed -n '2p' "$tmp/wakebodies" | grep -qF 'CI job hit its time cap on main: '
}
# capmsg <run id> <job> <ran minutes> <cap minutes> [suffix] [attempt]: the lines a cap-only wake posts for one job cancelled at its
# cap: the marker for the run and attempt (attempt 1 unless given), the title, and the job's cap line. Each line must be in the posted body.
capmsg() {
  printf '%s\n' "<!-- main-alarm:cap:$1:${6:-1} -->" "CI job hit its time cap on main: $2" "job $2 ran $3 min, cap $4 min, run $1${5:-}"
}
# woke <label> <run id> [attempt] [text]: the last case woke PR 7 once for that cap-end run and attempt (attempt 1 unless given): one
# pulls read of its head commit, one comments read of PR 7, and one post on PR 7 whose body holds the attempt's marker and the text.
woke() {
  local sha att="${3:-1}"
  sha="$(printf '%040x' "$2")"
  if ! { grep -qxF -- "pulls $sha" "$tmp/wakelog" && [ "$(wake_n pulls)" = 1 ] && grep -qxF -- "comments 7" "$tmp/wakelog" \
    && [ "$(wake_n comments)" = 1 ] && grep -qxF -- "post 7 o/r" "$tmp/wakelog" && [ "$(wake_n post)" = 1 ]; }; then
    echo "FAIL $1: the wake for run $2 was not one pulls read of its head, one comments read of PR 7 and one post on PR 7 (wake log: $(tr '\n' ' ' < "$tmp/wakelog"))"; bad=1
  elif ! grep -qF -- "<!-- main-alarm:cap:$2:$att -->" "$tmp/wakebodies"; then echo "FAIL $1: the post for run $2 lacks its marker cap:$2:$att"; bad=1
  elif [ -n "${4:-}" ] && ! grep -qF -- "$4" "$tmp/wakebodies"; then echo "FAIL $1: the post for run $2 lacks '$4'"; bad=1
  else echo "ok   $1"; fi
}
# body_has <label> <KEY> <text>: the post whose marker is <!-- main-alarm:KEY --> holds <text>. A text with a leading `!` must not be in
# that post. A post's lines run from its marker line to the next marker line.
body_has() {
  local got
  got="$(awk -v m="<!-- main-alarm:$2 -->" 'index($0, "<!-- main-alarm:") == 1 { f = ($0 == m); next } f' "$tmp/wakebodies")"
  if [ -z "$got" ]; then echo "FAIL $1: no post carries $2"; bad=1
  elif [[ "$3" == '!'* ]]; then
    if grep -qF -- "${3#!}" <<<"$got"; then echo "FAIL $1: the post for $2 holds '${3#!}'"; bad=1; else echo "ok   $1"; fi
  elif grep -qF -- "$3" <<<"$got"; then echo "ok   $1"
  else echo "FAIL $1: the post for $2 lacks '$3'"; bad=1; fi
}
# wake_is <label> <pulls> <comments> <posts>: the last case read the wake's pulls and PR comments that many times and posted that many.
wake_is() {
  local got
  got="$(wake_n pulls) $(wake_n comments) $(wake_n post)"
  if [ "$got" = "$2 $3 $4" ]; then echo "ok   $1"; else echo "FAIL $1: wake pulls, comments and posts were $got, want $2 $3 $4"; bad=1; fi
}
# cap_quiet <label> <zero|nonzero>: the last run of alarm.sh made no gh issue call, printed the verdict alarm, and exited as
# given. Each failure names its one cause.
cap_quiet() {
  local verdict
  verdict="$(tail -n 1 <<<"$out")"
  if [ -s "$tmp/issuecalls" ] || [ -s "$tmp/log" ]; then echo "FAIL $1: a gh issue call was made for a cap-only alarm"; bad=1
  elif [ "$verdict" != alarm ]; then echo "FAIL $1: the verdict is '$verdict', not alarm"; bad=1
  elif [ "$2" = zero ] && [ "$code" != 0 ]; then echo "FAIL $1: exit was $code, want 0"; bad=1
  elif [ "$2" = nonzero ] && [ "$code" = 0 ]; then echo "FAIL $1: exit was 0, want non-zero"; bad=1
  else echo "ok   $1"; fi
}
# quiet_wake <label>: the last case made no wake call at all.
quiet_wake() {
  if [ ! -s "$tmp/wakelog" ]; then echo "ok   $1"; else echo "FAIL $1: the wake log has: $(tr '\n' ' ' < "$tmp/wakelog")"; bad=1; fi
}
# t want label [FAIL glob] [EMPTY glob] [text ...] [jobs reads: "none", or the run paths read, in any order]. The wants:
# alarm, a cap end with no red run: the verdict is alarm, no gh issue call is made, and the wake reads the PR once and posts once,
# the body opening with the marker and the title; each text must be in that body. repeat: the same, but the PR already holds the
# marker, so the wake posts nothing. A text is one line; each must be in the issue (the wake body for alarm and repeat). A text
# with a leading `!` must not be there, and `!re:` makes the rest an extended regex that must not match.
t() {
  local why=""
  run_alarm "${3:-}" "${4:-}"
  shown="$(grep -v '^::\(warning\|notice\)::' <<<"$out")" # the verdict, without the workflow annotations, which are not the verdict
  ok=0
  case "$1" in
    green) [ "$shown" = green ] && [ ! -s "$tmp/log" ] && ok=1 ;;
    red) [ "$shown" = red ] && grep -q ISSUE "$tmp/log" && ok=1 ;;
    alarm)
      if [ "$shown" != alarm ]; then why="the verdict is not alarm"
      elif [ -s "$tmp/log" ] || [ -s "$tmp/issuecalls" ]; then why="a gh issue call was made for a cap-only alarm"
      elif [ "$(wake_n pulls)" != 1 ] || [ "$(wake_n comments)" != 1 ] || [ "$(wake_n post)" != 1 ]; then why="the wake did not read the PR once and post once"
      elif ! alarm_body; then why="the posted body does not open with the marker and the title"
      else ok=1; fi ;;
    repeat)
      if [ "$shown" != alarm ]; then why="the verdict is not alarm"
      elif [ -s "$tmp/log" ] || [ -s "$tmp/issuecalls" ]; then why="a gh issue call was made for a cap-only alarm"
      elif [ "$(wake_n pulls)" != 1 ] || [ "$(wake_n comments)" != 1 ]; then why="the wake did not read the PR once"
      elif [ "$(wake_n post)" != 0 ]; then why="the wake posted a comment the PR already holds"
      else ok=1; fi ;;
    raised) [ "$code" = 0 ] && grep -q ISSUE "$tmp/log" && ok=1 ;; # the issue opened; the verdict is not pinned
    unknown) [ "$shown" = unknown ] && [ ! -s "$tmp/log" ] && grep -q '::warning::' <<<"$out"$'\n'"$(cat "$tmp/err")" && ok=1 ;;
  esac
  [ "$code" = 0 ] || { ok=0; why="${why:-the exit was not 0}"; }
  target="$tmp/log"; what=issue
  case "$1" in alarm|repeat) target="$tmp/wakebodies"; what="wake body" ;; esac
  miss=""; hold=""
  while IFS= read -r want_text; do
    case "$want_text" in
      '') ;;
      '!re:'*) grep -qE -- "${want_text#'!re:'}" "$target" && { ok=0; hold="${hold:-$want_text}"; } ;;
      '!'*) grep -qF -- "${want_text#!}" "$target" && { ok=0; hold="${hold:-$want_text}"; } ;;
      *) grep -qF -- "$want_text" "$target" || { ok=0; miss="${miss:-$want_text}"; } ;;
    esac
  done <<<"${5:-}"
  if [ -n "${6:-}" ]; then
    expect_reads="$(tr ' ' '\n' <<<"$6" | grep -v '^none$' | sort | tr '\n' ' ')"
    got_reads="$(grep -o 'actions/runs/[0-9]*/jobs' "$tmp/reads" | sort | tr '\n' ' ')"
    [ "$expect_reads" = "$got_reads" ] || { ok=0; why="${why:-the jobs reads are not the ones expected}"; }
  fi
  if [ "$ok" = 1 ]; then echo "ok   $2"
  elif [ -n "$why" ]; then echo "FAIL $2 ($why; verdict '$shown', exit $code)"; bad=1
  elif [ -n "$hold" ]; then echo "FAIL $2 (verdict '$shown', exit $code; $what holds '$hold')"; bad=1
  elif [ -n "$miss" ]; then echo "FAIL $2 (verdict '$shown', exit $code; $what lacks '$miss')"; bad=1
  else echo "FAIL $2 (exit $code, got: $out; jobs reads: $(tr '\n' ' ' < "$tmp/reads"))"; bad=1; fi
}
runs_are "$(gh_run ci failure 2026-01-02 u1 push 1)" "$(gh_run ci success 2026-01-01 u0 push 2)"
t red latest-red-opens-issue
runs_are "$(gh_run ci success 2026-01-02 u1 push 1)" "$(gh_run ci failure 2026-01-01 u0 push 2)"
jobs_of 1 checks:success
jobs_of 2 checks:failure
t green red-then-fixed-is-quiet
runs_are "$(gh_run alarm failure 2026-01-02 u1 push 1)"
t green own-workflow-is-ignored
# named <green|notred> <label>: one run of alarm.sh. The last stdout line is the verdict: green exactly for green, else any
# verdict but red. A green case opens no issue at all; a notred case opens no red issue (titled "CI red on ...").
named() {
  local want="$1" label="$2" verdict all ok=1
  run_alarm "" ""
  all="$out"$'\n'"$(cat "$tmp/err")"
  verdict="$(tail -n 1 <<<"$out")"
  [ "$code" = 0 ] || ok=0
  case "$want" in
    green) [ "$verdict" = green ] && [ ! -s "$tmp/log" ] || ok=0 ;;
    notred) [ -n "$verdict" ] && [ "$verdict" != red ] && ! grep -q 'CI red on' "$tmp/log" || ok=0 ;;
  esac
  if [ "$ok" = 1 ]; then echo "ok   $label"; else echo "FAIL $label (exit $code, verdict: ${verdict:-none}; got: $all; issue log: $(tr '\n' ' ' < "$tmp/log"))"; bad=1; fi
}
runs_are "$(gh_run ci success 2026-01-02 u1 push 1)" "$(gh_run deploy timed_out 2026-01-01 u2 push 2)"
jobs_of 1 checks:success
t red one-red-workflow-among-green

# The empty push run (decision no-merge-onto-red-main): a green run of the push group that ran no suite job is no verdict unless it carries
# evidence (push-skip success and scope skipped). The alarm judges the group's newest run that is not empty, as merge.py does.
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 push 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
jobs_of 2 push-skip:success scope:success checks:skipped
t red empty-green-push-without-evidence-does-not-hide-an-older-red-push "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
jobs_of 2 scope:success checks:skipped
t red empty-green-dispatch-without-evidence-does-not-hide-an-older-red-push "" "" https://runs/red-1
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 push 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
jobs_of 2 push-skip:success scope:skipped checks:skipped
t green empty-green-push-with-evidence-clears-an-older-red-push "" ""
runs_are "$(gh_run ci success 2026-01-02 https://runs/green-2 push 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
jobs_of 2 scope:success
t unknown empty-green-push-whose-jobs-read-fails-is-unknown "api *actions/runs/2/jobs*"

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
t red green-run-still-going-clears-nothing "" "" https://runs/red-1 "actions/runs/1/jobs"
runs_are "$(gh_run ci failure 2026-01-03 https://runs/red-3 schedule 3)" "$(gh_run ci success 2026-01-02 https://runs/green-2 schedule 2)" "$(gh_run ci failure 2026-01-01 https://runs/red-1 push 1)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
jobs_of 3 checks:failure
t red green-run-that-is-not-the-newest-of-its-group-clears-nothing "" "" https://runs/red-1 "actions/runs/1/jobs actions/runs/3/jobs"
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-1 push 1)" "$(gh_run ci success 2026-01-01 https://runs/green-2 schedule 2)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
t red green-run-older-than-the-red-run-clears-nothing "" "" https://runs/red-1 "actions/runs/1/jobs"
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
t red red-run-with-no-candidate-reads-its-jobs-once "" "" https://runs/red-1 "actions/runs/1/jobs"
# A cancelled run raises the alarm only through a job cancelled at its own job-level cap. Its jobs and its workflow file are each read once.
runs_are "$(gh_run ci cancelled 2026-01-02 u1 push 1)"
jobs_of 1 checks:cancelled:2
workflow_at 1 checks:20
t green cancelled-run-is-not-red "" "" "" "actions/runs/1/jobs"

# A job cancelled at its cap (elapsed >= cap, the cap read from the workflow file at the run's head) raises the alarm: the issue
# names the job, the cap and the run id. These cases pin the alarm, not the verdict. The quiet cases below stay quiet. The unknown
# cases are never red and never clear.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-exact push 4711)"
jobs_of 4711 scope-guard:cancelled:37
workflow_at 4711 scope-guard:37
t alarm job-cancelled-at-its-cap-raises-the-alarm "" "" "$(capmsg 4711 scope-guard 37 37)" "actions/runs/4711/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-over push 4712)"
jobs_of 4712 scope-guard:cancelled:40
workflow_at 4712 scope-guard:37
t alarm job-over-its-cap-names-the-job-the-cap-and-the-run "" "" "$(capmsg 4712 scope-guard 40 37)" "actions/runs/4712/jobs"
cost over-cap-red-reads-one-jobs-list-and-one-workflow-file-and-starts-one-python 1 1 1 1
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-mixed push 4715)"
jobs_of 4715 build:success:10 scope-guard:cancelled:40
workflow_at 4715 build:20 scope-guard:37
t alarm one-job-over-its-cap-among-passed-jobs-raises-the-alarm "" "" "$(capmsg 4715 scope-guard 40 37)" "actions/runs/4715/jobs"

runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-under push 4713)"
jobs_of 4713 scope-guard:cancelled:2 other:success
workflow_at 4713 scope-guard:37 other:37
t green job-cancelled-well-under-its-cap-is-quiet "" "" ""
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-skip push 4714)"
jobs_of 4714 scope-guard:skipped:40 other:success:40
workflow_at 4714 scope-guard:37 other:37
t green skipped-and-passed-jobs-are-not-judged-by-the-cap "" "" ""

runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-nocap push 4716)"
jobs_of 4716 scope-guard:cancelled:40
workflow_at 4716 scope-guard
t green job-cancelled-with-no-cap-under-the-360-minute-default-is-quiet "" "" "" "actions/runs/4716/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-absent push 4717)"
jobs_of 4717 scope-guard:cancelled:40
workflow_at 4717 other-job:37
t unknown job-cancelled-and-absent-from-the-workflow-is-unknown-not-clear "" "" "" "actions/runs/4717/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-never push 4718)"
jobs_of 4718 scope-guard:cancelled:never
workflow_at 4718 scope-guard:37
t unknown job-cancelled-that-never-started-is-unknown-not-clear "" "" "" "actions/runs/4718/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-unread push 4719)"
jobs_of 4719 scope-guard:cancelled:40
t unknown job-cancelled-with-an-unreadable-workflow-is-unknown-not-clear "api *contents/*" "" "" "actions/runs/4719/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-empty push 4720)"
jobs_of 4720
workflow_at 4720 scope-guard:37
t unknown cancelled-run-with-no-jobs-is-unknown-not-clear "" "" "" "actions/runs/4720/jobs"

# A job with no job-level timeout-minutes has GitHub's default cap, 360 minutes: cancelled at 360 it raises the alarm, under it it is quiet.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/nocap-360 push 4741)"
jobs_of 4741 scope-guard:cancelled:360
workflow_at 4741 scope-guard
t alarm job-cancelled-at-360-minutes-with-no-cap-raises-the-alarm "" "" "$(capmsg 4741 scope-guard 360 360)"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/nocap-359 push 4742)"
jobs_of 4742 scope-guard:cancelled:359
workflow_at 4742 scope-guard
t green job-cancelled-at-359-minutes-with-no-cap-is-quiet "" "" ""

# Every cancelled run in the window is judged, not only the newest cancelled run of its group. A cap end under a newer green run of the
# same group still opens the cap-only alarm. Each judged cancelled run reads its jobs once and its workflow file once.
runs_are "$(gh_run ci success 2026-01-02 https://runs/newer-green-5201 push 5201)" "$(gh_run ci cancelled 2026-01-01 https://runs/older-cap-5200 push 5200)"
jobs_of 5201 checks:success
jobs_of 5200 scope-guard:cancelled:40
workflow_at 5200 scope-guard:37
t alarm older-cancelled-cap-end-under-a-newer-green-run-opens-the-cap-alarm "" "" "$(capmsg 5200 scope-guard 40 37)"
cost older-cancelled-cap-end-under-a-newer-green-run-reads-its-jobs-and-workflow-once 2 1 2 1
runs_are "$(gh_run ci success 2026-01-02 https://runs/newer-green-5211 push 5211)" "$(gh_run ci cancelled 2026-01-01 https://runs/older-under-cap-5210 push 5210)"
jobs_of 5211 checks:success
jobs_of 5210 scope-guard:cancelled:2
workflow_at 5210 scope-guard:37
t green older-cancelled-under-its-cap-under-a-newer-green-run-stays-quiet "" "" ""
cost older-cancelled-under-its-cap-under-a-newer-green-run-reads-its-jobs-and-workflow-once 2 1 2
# Two cancelled runs in the window: the older is over its cap and the newer is under it. The alarm names the older run.
runs_are "$(gh_run ci cancelled 2026-01-01 https://runs/two-older-over-cap-5220 push 5220)" "$(gh_run ci cancelled 2026-01-02 https://runs/two-newer-under-cap-5221 push 5221)"
jobs_of 5220 scope-guard:cancelled:40
jobs_of 5221 scope-guard:cancelled:2
workflow_at 5220 scope-guard:37
workflow_at 5221 scope-guard:37
t alarm two-cancelled-runs-the-older-over-its-cap-names-the-older-run "" "" "$(capmsg 5220 scope-guard 40 37)"
cost two-cancelled-runs-each-read-their-jobs-and-workflow-once 2 2 1 1
# A full run window of 100 runs: the oldest is a cancelled cap end and the 99 newer ones succeeded. The cap end still opens the alarm.
window=(); for i in $(seq 1 99); do window+=("$(gh_run ci success 2026-01-02 "https://runs/window-green-$i" push $((5300 + i)))"); done
runs_are "$(gh_run ci cancelled 2026-01-01 https://runs/window-oldest-cap-5300 push 5300)" "${window[@]}"
jobs_of 5399 checks:success
jobs_of 5300 scope-guard:cancelled:40
workflow_at 5300 scope-guard:37
t alarm full-run-window-oldest-cancelled-cap-end-opens-the-cap-alarm "" "" "$(capmsg 5300 scope-guard 40 37)"
cost full-run-window-oldest-cancelled-cap-end-reads-its-jobs-and-workflow-once 2 1 2 1
# A failure run whose only red job was cancelled at its cap is red by its conclusion. Its cap end wakes the run, and the red issue
# names no cap end. Only the issue is pinned here, not the verdict.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/fail-cap-4740 push 4740)"
jobs_of 4740 scope-guard:cancelled:40
workflow_at 4740 scope-guard:37
t raised failure-run-with-its-only-red-job-cancelled-at-its-cap-keeps-the-cap-end-out-of-the-issue "" "" "!re:ran [0-9]+ min, cap [0-9]+ min"
woke failure-run-cap-end-wakes-the-pr-beside-its-red-job 4740 1 "job scope-guard ran 40 min, cap 37 min, run 4740"

# A cap end with no red run is the alarm, not a red verdict: the verdict word is `alarm`. The control puts the same cap end (in ci)
# beside a red failure run (in deploy) in one fixture, and the verdict stays `red`, and the red issue names no cap end.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/alarm-only-5020 push 5020)"
jobs_of 5020 scope-guard:cancelled:40
workflow_at 5020 scope-guard:37
t alarm cap-end-only-run-prints-the-alarm-verdict "" "" "$(capmsg 5020 scope-guard 40 37)" "actions/runs/5020/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/alarm-beside-red-5030 push 5030)" "$(gh_run deploy failure 2026-01-02 https://runs/red-beside-cap-5031 push 5031)"
jobs_of 5030 scope-guard:cancelled:40
jobs_of 5031 checks:failure
workflow_at 5030 scope-guard:37
t red red-run-beside-a-cap-end-still-prints-red "" "" "$(printf '%s\n' '--title CI red on main --body' '!re:ran [0-9]+ min, cap [0-9]+ min')" "actions/runs/5030/jobs actions/runs/5031/jobs"
woke red-run-beside-a-cap-end-still-wakes-for-the-cap-end 5030 1 "job scope-guard ran 40 min, cap 37 min, run 5030"

# The cap-only alarm's title names its job: "CI job hit its time cap on <branch>: <job>". With several cap jobs the title names the
# first in the run's job list and the body names the rest. Here scope-guard comes before build-guard in both the job list and the
# workflow file, and build-guard sorts first, so the title pins list order, not alphabetical order.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-title-5021 push 5021)"
jobs_of 5021 scope-guard:cancelled:40
workflow_at 5021 scope-guard:37
t alarm cap-only-alarm-title-names-its-job "" "" "$(capmsg 5021 scope-guard 40 37)" "actions/runs/5021/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cap-titles-5022 push 5022)"
jobs_of 5022 scope-guard:cancelled:40 build-guard:cancelled:50
workflow_at 5022 scope-guard:37 build-guard:37
t alarm cap-only-alarm-with-several-cap-jobs-titles-the-first-and-names-the-rest "" "" "$(capmsg 5022 scope-guard 40 37; echo 'job build-guard ran 50 min, cap 37 min, run 5022')" "actions/runs/5022/jobs"
# A red job and a cap end in one failure run: the run is red, so the title stays "CI red on", and the cap end wakes the run while the
# red issue names no cap end.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/mixed-same-5040 push 5040)"
jobs_of 5040 checks:failure scope-guard:cancelled:40
workflow_at 5040 checks scope-guard:37
t red mixed-run-with-a-red-job-and-a-cap-end-keeps-the-red-title "" "" "$(printf '%s\n' '--title CI red on main --body' '!re:ran [0-9]+ min, cap [0-9]+ min')" "actions/runs/5040/jobs"
woke mixed-run-cap-end-wakes-for-the-run 5040 1 "job scope-guard ran 40 min, cap 37 min, run 5040"

# A job cancelled at its cap in attempt 1 of a run whose attempt 2 is green opens the cap-only alarm: the title names the job, and the
# body names the run. Attempt 1's jobs come from the attempts endpoint; the latest attempt's jobs do not hold them.
runs_are "$(gh_run ci success 2026-01-02 https://runs/retry-cap-4750 push 4750 completed 2)"
attempt_jobs_of 4750 1 scope-guard:cancelled:40
jobs_of 4750 scope-guard:success
workflow_at 4750 scope-guard:37
t alarm cap-end-in-attempt-1-of-a-green-run-opens-the-cap-alarm "" "" "$(capmsg 4750 scope-guard 40 37)"
count_is cap-end-in-attempt-1-of-a-green-run-reads-attempt-1-jobs-once "actions/runs/4750/attempts/1/jobs" 1
count_is cap-end-in-attempt-1-of-a-green-run-reads-its-workflow-file-once "/contents/" 1
# Controls: a green run whose earlier attempt has no cap end stays silent.
runs_are "$(gh_run ci success 2026-01-02 https://runs/retry-under-4751 push 4751 completed 2)"
attempt_jobs_of 4751 1 scope-guard:cancelled:2
jobs_of 4751 scope-guard:success
workflow_at 4751 scope-guard:37
named green attempt-1-cancelled-under-its-cap-in-a-green-run-stays-silent
count_is attempt-1-under-its-cap-in-a-green-run-reads-attempt-1-jobs-once "actions/runs/4751/attempts/1/jobs" 1
runs_are "$(gh_run ci success 2026-01-02 https://runs/retry-clean-4752 push 4752 completed 2)"
attempt_jobs_of 4752 1 scope-guard:success
jobs_of 4752 scope-guard:success
workflow_at 4752 scope-guard:37
named green green-run-with-no-cap-end-in-any-attempt-stays-silent
# An older succeeded re-run is judged under a newer green run of its group: the re-run list is every succeeded re-run in the window,
# not only each group's newest run. Only the older run's earlier attempt holds the cap end, so a read of the newest run alone misses it.
runs_are "$(gh_run ci success 2026-01-01 https://runs/older-retry-cap-6010 push 6010 completed 2)" "$(gh_run ci success 2026-01-02 https://runs/newer-green-6011 push 6011)"
jobs_of 6011 checks:success
attempt_jobs_of 6010 1 scope-guard:cancelled:40
workflow_at 6010 scope-guard:37
t alarm older-rerun-under-a-newer-green-run-opens-the-cap-alarm "" "" "$(capmsg 6010 scope-guard 40 37 ', attempt 1')"
count_is older-rerun-under-a-newer-green-run-reads-attempt-1-jobs-once "actions/runs/6010/attempts/1/jobs" 1
# Control: the same older re-run with attempt 1 cancelled under its cap, under the same newer green run, stays silent.
runs_are "$(gh_run ci success 2026-01-01 https://runs/older-retry-under-6012 push 6012 completed 2)" "$(gh_run ci success 2026-01-02 https://runs/newer-green-6013 push 6013)"
jobs_of 6013 checks:success
attempt_jobs_of 6012 1 scope-guard:cancelled:2
workflow_at 6012 scope-guard:37
t green older-rerun-under-its-cap-under-a-newer-green-run-stays-silent "" ""
count_is older-rerun-under-its-cap-reads-attempt-1-jobs-once "actions/runs/6012/attempts/1/jobs" 1
# A failure run with a red job in its newest attempt and a cap end in attempt 1: the title stays "CI red on", and the red issue
# names no cap end while the wake does.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/red-retry-cap-5230 push 5230 completed 2)"
attempt_jobs_of 5230 1 scope-guard:cancelled:40
jobs_of 5230 checks:failure scope-guard:success
workflow_at 5230 checks scope-guard:37
t red red-run-with-a-cap-end-in-attempt-1-keeps-the-cap-end-out-of-the-issue "" "" "$(printf '%s\n' '--title CI red on main --body' '!re:ran [0-9]+ min, cap [0-9]+ min')"
woke red-run-with-a-cap-end-in-attempt-1-wakes-for-the-cap-end 5230 1 "job scope-guard ran 40 min, cap 37 min, run 5230"
count_is red-run-with-a-cap-end-in-attempt-1-reads-attempt-1-jobs-once "actions/runs/5230/attempts/1/jobs" 1
count_is red-run-with-a-cap-end-in-attempt-1-reads-its-newest-jobs-once "actions/runs/5230/jobs" 1
count_is red-run-with-a-cap-end-in-attempt-1-reads-its-workflow-file-once "/contents/" 1

# A failure run that a newer run of its group supersedes is judged for its cap end. A job cancelled at its cap wakes the PR for that
# run, and the alarm opens no issue. Its jobs and its workflow file are each read once. The controls read its jobs once and wake nothing.
runs_are "$(gh_run ci failure 2026-01-01 https://runs/stale-cap-7010 push 7010)" "$(gh_run ci success 2026-01-02 https://runs/stale-cap-green-7011 push 7011)"
jobs_of 7011 checks:success
jobs_of 7010 scope-guard:cancelled:40
workflow_at 7010 scope-guard:37
t alarm failure-run-not-newest-with-a-cap-end-wakes-the-pr "" "" "$(capmsg 7010 scope-guard 40 37)" "actions/runs/7010/jobs actions/runs/7011/jobs"
woke failure-run-not-newest-cap-end-wakes-for-that-run 7010
cost failure-run-not-newest-cap-end-reads-its-jobs-and-workflow-once 2 1 2 1
stale_window=(); for i in $(seq 1 99); do stale_window+=("$(gh_run ci success 2026-01-02 "https://runs/stale-window-green-$i" push $((7100 + i)))"); done
runs_are "$(gh_run ci failure 2026-01-01 https://runs/stale-window-oldest-7100 push 7100)" "${stale_window[@]}"
jobs_of 7199 checks:success
jobs_of 7100 scope-guard:cancelled:40
workflow_at 7100 scope-guard:37
t alarm failure-run-not-newest-in-a-full-window-wakes-the-pr "" "" "$(capmsg 7100 scope-guard 40 37)" "actions/runs/7100/jobs actions/runs/7199/jobs"
woke failure-run-not-newest-in-a-full-window-wakes-for-that-run 7100
# A cap end in an earlier attempt of a failure run that a newer run of its group supersedes wakes the PR for that run. The newest
# attempt holds no cap end; the attempts endpoint does. The control has the same shape with that attempt under its cap, and stays quiet.
runs_are "$(gh_run ci success 2026-01-02 https://runs/stale-retry-green-7201 push 7201)" "$(gh_run ci failure 2026-01-01 https://runs/stale-retry-red-7200 push 7200 completed 2)"
jobs_of 7201 checks:success
attempt_jobs_of 7200 1 scope-guard:cancelled:40
jobs_of 7200 checks:failure scope-guard:success
workflow_at 7200 checks scope-guard:37
t alarm failure-run-not-newest-cap-end-in-attempt-1-wakes-the-pr "" "" "$(capmsg 7200 scope-guard 40 37 ', attempt 1')" "actions/runs/7200/jobs actions/runs/7201/jobs"
count_is failure-run-not-newest-cap-end-in-attempt-1-reads-attempt-1-jobs-once "actions/runs/7200/attempts/1/jobs" 1
runs_are "$(gh_run ci success 2026-01-02 https://runs/stale-retry-under-green-7221 push 7221)" "$(gh_run ci failure 2026-01-01 https://runs/stale-retry-under-red-7220 push 7220 completed 2)"
jobs_of 7221 checks:success
attempt_jobs_of 7220 1 scope-guard:cancelled:2
jobs_of 7220 checks:failure scope-guard:success
workflow_at 7220 checks scope-guard:37
t green failure-run-not-newest-cap-end-in-attempt-1-under-its-cap-stays-quiet "" "" ""
runs_are "$(gh_run ci failure 2026-01-01 https://runs/stale-red-7020 push 7020)" "$(gh_run ci success 2026-01-02 https://runs/stale-red-green-7021 push 7021)"
jobs_of 7021 checks:success
jobs_of 7020 checks:failure
t green failure-run-not-newest-with-no-cap-end-stays-quiet
quiet_wake failure-run-not-newest-with-no-cap-end-makes-no-wake
count_is failure-run-not-newest-with-no-cap-end-reads-its-jobs-once "actions/runs/7020/jobs" 1
runs_are "$(gh_run ci failure 2026-01-01 https://runs/stale-under-7030 push 7030)" "$(gh_run ci success 2026-01-02 https://runs/stale-under-green-7031 push 7031)"
jobs_of 7031 checks:success
jobs_of 7030 scope-guard:cancelled:2
workflow_at 7030 scope-guard:37
t green failure-run-not-newest-with-a-cap-job-under-its-cap-stays-quiet
quiet_wake failure-run-not-newest-with-a-cap-job-under-its-cap-makes-no-wake
count_is failure-run-not-newest-with-a-cap-job-under-its-cap-reads-its-jobs-once "actions/runs/7030/jobs" 1
# A failure run that a newer run of its group supersedes is never red. When its jobs read fails, the alarm is unknown, not green: the
# unread jobs may hold a cap end.
runs_are "$(gh_run ci success 2026-01-02 https://runs/stale-unread-green-7211 push 7211)" "$(gh_run ci failure 2026-01-01 https://runs/stale-unread-red-7210 push 7210)"
jobs_of 7211 checks:success
t unknown failure-run-not-newest-with-an-unreadable-jobs-read-is-unknown-not-green "api *actions/runs/7210/jobs*" "" "" "actions/runs/7210/jobs actions/runs/7211/jobs"
# A re-run in flight is the group's newest run: its status is in_progress or queued and its attempt is above 1. The group is
# UNKNOWN (main's judged rule, merge/merge.py base_state), so the alarm reads unknown with a warning and writes no issue. It never
# reads green, and never falls back to an older run. A first attempt still in progress waits its turn, so the older run is judged (1d).
runs_are "$(gh_run ci failure 2026-01-01 https://runs/rerun-red-4901 push 4901)" "$(gh_run ci null 2026-01-02 https://runs/rerun-4902 push 4902 in_progress 2)"
jobs_of 4901 checks:failure
t unknown rerun-in-flight-hides-an-older-red-run-as-unknown-not-red "" "" ""
# A queued re-run does not hide an older cancelled cap end: a cap end on main opens its issue whatever the group's newest run is doing.
runs_are "$(gh_run ci cancelled 2026-01-01 https://runs/rerun-cap-4910 push 4910)" "$(gh_run ci null 2026-01-02 https://runs/rerun-queued-4911 push 4911 queued 2)"
jobs_of 4910 scope-guard:cancelled:40
workflow_at 4910 scope-guard:37
t alarm rerun-queued-does-not-hide-an-older-cap-end "" "" "$(capmsg 4910 scope-guard 40 37)"
cost rerun-queued-does-not-hide-an-older-cap-end-reads-its-jobs-and-workflow-once 1 1 1 1
runs_are "$(gh_run ci success 2026-01-01 https://runs/rerun-green-4920 push 4920)" "$(gh_run ci null 2026-01-02 https://runs/rerun-4921 push 4921 in_progress 2)"
jobs_of 4920 checks:success
t unknown rerun-in-flight-is-not-green-from-an-older-green-run "" "" ""
runs_are "$(gh_run ci failure 2026-01-01 https://runs/first-red-4930 push 4930)" "$(gh_run ci null 2026-01-02 https://runs/first-attempt-4931 push 4931 in_progress 1)"
jobs_of 4930 checks:failure
t red first-attempt-in-flight-waits-its-turn-and-the-older-red-run-is-judged "" "" ""

# A cancelled newest run (attempt 2) names a job cancelled at its cap in attempt 1: the alarm reads every attempt, not only the
# newest. The newest attempt shows the job short, so only the earlier attempt holds the cap end. Each earlier attempt is read once.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cancel-retry-4940 push 4940 completed 2)"
attempt_jobs_of 4940 1 scope-guard:cancelled:40 checks:success:5
jobs_of 4940 scope-guard:cancelled:2 checks:success:5
workflow_at 4940 scope-guard:37 checks
t alarm cancelled-rerun-names-a-cap-end-in-attempt-1 "" "" "$(capmsg 4940 scope-guard 40 37)" "actions/runs/4940/jobs"
count_is cancelled-rerun-reads-attempt-1-jobs-once "actions/runs/4940/attempts/1/jobs" 1
# Controls: attempt 1 cancelled under its cap stays quiet.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cancel-retry-under-4941 push 4941 completed 2)"
attempt_jobs_of 4941 1 scope-guard:cancelled:2
jobs_of 4941 scope-guard:cancelled:2
workflow_at 4941 scope-guard:37
t green cancelled-rerun-with-attempt-1-cancelled-under-its-cap-is-quiet "" "" ""
# Attempt 1 unread is unknown, never green. Attempt 1 with no jobs is unknown too: no cap end can be read from it (the no-jobs rule).
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cancel-retry-unread-4942 push 4942 completed 2)"
attempt_jobs_of 4942 1 scope-guard:cancelled:40
jobs_of 4942 scope-guard:cancelled:2
workflow_at 4942 scope-guard:37
t unknown cancelled-rerun-with-attempt-1-unread-is-unknown-not-green "api *attempts/1/jobs*" "" ""
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/cancel-retry-empty-4943 push 4943 completed 2)"
attempt_jobs_of 4943 1
jobs_of 4943 scope-guard:cancelled:2
workflow_at 4943 scope-guard:37
t unknown cancelled-rerun-with-attempt-1-without-jobs-is-unknown-not-green "" "" ""

# A failed run that a newer green run of the other group clears is not red, but a cap end in it still opens an issue: the cap-only
# alarm, titled with the cap wording. Each of its two runs is read once, and its own workflow file is read once for the cap.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-cap-green-4951 schedule 4951)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-cap-red-4950 push 4950)"
jobs_of 4950 checks:failure scope-guard:cancelled:40
jobs_of 4951 checks:success scope-guard:success
workflow_at 4950 checks scope-guard:37
workflow_at 4951 checks scope-guard:37
t alarm failure-run-cleared-by-a-newer-green-with-a-cap-end-wakes-the-pr "" "" "$(capmsg 4950 scope-guard 40 37)" "actions/runs/4950/jobs actions/runs/4951/jobs"
cost cleared-run-with-a-cap-end-reads-each-jobs-list-once-and-each-workflow-file-once 2 2 3 1
count_is cleared-run-reads-its-jobs-once "actions/runs/4950/jobs" 1
count_is clearing-run-reads-its-jobs-once "actions/runs/4951/jobs" 1
# A cleared failure run's cap end wakes when another run is red too: the title stays "CI red on", and the red issue names no cap end.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-beside-green-5060 schedule 5060)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-beside-red-5061 push 5061)" "$(gh_run deploy failure 2026-01-02 https://runs/cleared-beside-deploy-5062 push 5062)"
jobs_of 5061 checks:failure scope-guard:cancelled:40
jobs_of 5060 checks:success scope-guard:success
jobs_of 5062 checks:failure
workflow_at 5061 checks scope-guard:37
workflow_at 5060 checks scope-guard:37
t red cleared-cap-run-beside-an-uncleared-red-run-keeps-the-cap-end-out-of-the-issue "" "" "$(printf '%s\n' '--title CI red on main --body' '!re:ran [0-9]+ min, cap [0-9]+ min')" "actions/runs/5060/jobs actions/runs/5061/jobs actions/runs/5062/jobs"
woke cleared-cap-run-beside-an-uncleared-red-run-wakes-for-the-cap-end 5061 1 "job scope-guard ran 40 min, cap 37 min, run 5061"
# A red job the newer green run lacks stays red, so a cap end beside it keeps the red title. The green run passes checks and has no lint job.
runs_are "$(gh_run ci success 2026-01-02 https://runs/partial-green-5043 schedule 5043)" "$(gh_run ci failure 2026-01-01 https://runs/partial-red-5042 push 5042)"
jobs_of 5042 checks:failure lint:failure scope-guard:cancelled:40
jobs_of 5043 checks:success scope-guard:success
workflow_at 5042 checks scope-guard:37
t red cap-end-beside-a-red-job-the-green-run-lacks-keeps-the-red-title "" "" "$(printf '%s\n' '--title CI red on main --body' '!re:ran [0-9]+ min, cap [0-9]+ min')" "actions/runs/5042/jobs actions/runs/5043/jobs"
woke cap-end-beside-a-red-job-wakes-for-the-cap-end 5042 1 "job scope-guard ran 40 min, cap 37 min, run 5042"
# Control: the same clear with the cap end under its cap is quiet. Its workflow file is still read once, for the cap.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-under-green-4953 schedule 4953)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-under-red-4952 push 4952)"
jobs_of 4952 checks:failure scope-guard:cancelled:2
jobs_of 4953 checks:success scope-guard:success
workflow_at 4952 checks scope-guard:37
workflow_at 4953 checks scope-guard:37
t green failure-run-cleared-by-a-newer-green-with-its-cap-end-under-the-cap-is-quiet "" "" ""
cost failure-run-cleared-by-a-newer-green-with-its-cap-end-under-the-cap-reads-its-workflow-file 2 2 3

# A cap end in an earlier attempt of a failure run that a newer green run clears still opens the cap-only alarm. The newest
# attempt of the failed run does not hold that cap end; the attempts endpoint does. The control has the same shape with the
# cancelled job under its cap, and stays quiet.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-retry-green-5100 schedule 5100)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-retry-red-5101 push 5101 completed 2)"
attempt_jobs_of 5101 1 scope-guard:cancelled:40
jobs_of 5101 checks:failure scope-guard:success
jobs_of 5100 checks:success scope-guard:success
workflow_at 5101 checks scope-guard:37
workflow_at 5100 checks scope-guard:37
t alarm cleared-failure-run-with-a-cap-end-in-attempt-1-opens-the-cap-alarm "" "" "$(capmsg 5101 scope-guard 40 37)"
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-retry-under-green-5110 schedule 5110)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-retry-under-red-5111 push 5111 completed 2)"
attempt_jobs_of 5111 1 scope-guard:cancelled:2
jobs_of 5111 checks:failure scope-guard:success
jobs_of 5110 checks:success scope-guard:success
workflow_at 5111 checks scope-guard:37
workflow_at 5110 checks scope-guard:37
t green cleared-failure-run-with-attempt-1-cancelled-under-its-cap-is-quiet "" "" ""

# A cleared failure run whose cap end cannot be judged is unknown: a warning and no issue, never green. Here the cancelled job
# has no start time, so its run time cannot be read.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-never-green-5120 schedule 5120)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-never-red-5121 push 5121)"
jobs_of 5121 checks:failure scope-guard:cancelled:never
jobs_of 5120 checks:success scope-guard:success
workflow_at 5121 checks scope-guard:37
workflow_at 5120 checks scope-guard:37
t unknown cleared-failure-run-with-a-cap-job-that-never-started-is-unknown-not-green "" "" ""
# Here only the failed run's workflow file is unreadable. The fail glob matches that one contents read, so the clearing run's
# file still reads and the clear is still judged, and the cap end is what cannot be.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-nofile-green-5130 schedule 5130)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-nofile-red-5131 push 5131)"
jobs_of 5131 checks:failure scope-guard:cancelled:40
jobs_of 5130 checks:success scope-guard:success
workflow_at 5131 checks scope-guard:37
workflow_at 5130 checks scope-guard:37
t unknown cleared-failure-run-whose-workflow-file-is-unreadable-is-unknown-not-green "api *ref=$(printf '%040x' 5131)" "" ""
# An earlier attempt that cannot be read may hold a cap end, so the cleared failure run is unknown, never green.
runs_are "$(gh_run ci success 2026-01-02 https://runs/cleared-unread-green-5140 schedule 5140)" "$(gh_run ci failure 2026-01-01 https://runs/cleared-unread-red-5141 push 5141 completed 2)"
jobs_of 5141 checks:failure scope-guard:success
jobs_of 5140 checks:success scope-guard:success
workflow_at 5141 checks scope-guard:37
workflow_at 5140 checks scope-guard:37
t unknown cleared-failure-run-with-attempt-1-unread-is-unknown-not-green "api *attempts/1/jobs*" "" ""

# Reads per judged run, counted in the call log (the reads the alarm made, not the text of its description). One jobs read per
# judged run. Every alarm that reaches the walk starts python3 once for the rule-events list, so a failed run with a red job and no
# clear candidate starts that one python3 and nothing else. A run cleared by a candidate reads the candidate's jobs once and its
# workflow file once, and starts clear_rule.py twice more (the red-stays step, then the clear step).
runs_are "$(gh_run ci failure 2026-01-02 https://runs/count-red-4960 push 4960)"
jobs_of 4960 checks:failure
t red one-judged-failed-run-reads-its-jobs-once "" "" "" "actions/runs/4960/jobs"
cost one-judged-failed-run-reads-its-jobs-once-and-starts-one-python 1 0 1
runs_are "$(gh_run ci failure 2026-01-02 https://runs/count-capped-4963 push 4963)"
jobs_of 4963 scope-guard:cancelled:40
workflow_at 4963 scope-guard:37
t red one-judged-failed-run-with-a-cap-end-reads-its-jobs-and-workflow-once "" "" "" "actions/runs/4963/jobs"
woke one-judged-failed-run-with-a-cap-end-wakes-for-the-cap-end 4963
cost one-judged-failed-run-with-a-cap-end-reads-one-workflow-file-and-starts-one-python 1 1 1 1
runs_are "$(gh_run ci success 2026-01-02 https://runs/count-green-4962 schedule 4962)" "$(gh_run ci failure 2026-01-01 https://runs/count-red-4961 push 4961)"
jobs_of 4961 checks:failure
jobs_of 4962 checks:success
t green one-red-run-cleared-by-a-candidate-reads-each-jobs-list-once "" "" "" "actions/runs/4961/jobs actions/runs/4962/jobs"
cost one-red-run-cleared-by-a-candidate-reads-one-workflow-file-and-starts-python-three-times 2 1 3

# A cap end with no red run wakes its pull request once, through wake.sh, and opens no issue. The pull request is PR 7 merged
# into main, and it holds no comments unless a case says so.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/wake-pr-5401 push 5401)"
jobs_of 5401 scope-guard:cancelled:40
workflow_at 5401 scope-guard:37
t alarm cap-only-wakes-the-merged-pr-and-opens-no-issue "" "" "$(capmsg 5401 scope-guard 40 37)" "actions/runs/5401/jobs"
woke cap-only-wake-is-for-the-run-and-its-head-commit 5401
# A cap end whose pull request already holds its marker wakes nothing: the verdict is still alarm, and the wake reads the PR.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/wake-repeat-5410 push 5410)"
jobs_of 5410 scope-guard:cancelled:40
workflow_at 5410 scope-guard:37
wake_comments_on 7 '[{"body": "<!-- main-alarm:cap:5410:1 -->\nalready woken"}]'
t repeat cap-end-the-pr-already-holds-posts-nothing "" "" "" "actions/runs/5410/jobs"
# The marker sits on comments page two, behind a full first page: the wake still reads every page and posts nothing.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/wake-repeat-page-two-5411 push 5411)"
jobs_of 5411 scope-guard:cancelled:40
workflow_at 5411 scope-guard:37
full_page="$(jq -cn '[range(30) | {body: "unrelated comment \(.)"}]')"
wake_comments_on 7 "$full_page" '[{"body": "<!-- main-alarm:cap:5411:1 -->\nalready woken"}]'
t repeat cap-end-whose-marker-is-on-comments-page-two-posts-nothing "" "" "" "actions/runs/5411/jobs"
# A marker for another cap end does not name this one: the wake posts.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/wake-other-5420 push 5420)"
jobs_of 5420 scope-guard:cancelled:40
workflow_at 5420 scope-guard:37
wake_comments_on 7 '[{"body": "<!-- main-alarm:cap:5419:1 -->\nan earlier cap end"}]'
t alarm cap-end-the-pr-holds-only-another-run-still-wakes "" "" "$(capmsg 5420 scope-guard 40 37)" "actions/runs/5420/jobs"
# Two cap-end runs, the older already named on the PR: each run reads the PR, and only the newer one posts.
runs_are "$(gh_run ci cancelled 2026-01-01 https://runs/wake-named-5431 push 5431)" "$(gh_run ci cancelled 2026-01-02 https://runs/wake-new-5432 push 5432)"
jobs_of 5431 scope-guard:cancelled:40
jobs_of 5432 build-guard:cancelled:41
workflow_at 5431 scope-guard:37
workflow_at 5432 build-guard:37
wake_comments_on 7 '[{"body": "<!-- main-alarm:cap:5431:1 -->\nalready woken"}]'
run_alarm
cap_quiet two-cap-runs-one-named-verdict-is-alarm-with-no-issue zero
wake_is two-cap-runs-one-named-each-run-reads-the-pr-and-only-the-new-run-posts 2 2 1
# The new run's title names its own first cap job (build-guard), not the older run's (scope-guard).
if grep -qF -- "<!-- main-alarm:cap:5432:1 -->" "$tmp/wakebodies" && ! grep -qF -- "cap:5431" "$tmp/wakebodies"; then echo "ok   two-cap-runs-one-named-posts-the-new-run-only"
else echo "FAIL two-cap-runs-one-named-posts-the-new-run-only: the posted bodies do not name run 5432 alone ($(tr '\n' ' ' < "$tmp/wakebodies"))"; bad=1; fi
if sed -n '2p' "$tmp/wakebodies" | grep -qxF -- "CI job hit its time cap on main: build-guard"; then echo "ok   two-cap-runs-one-named-title-names-the-new-runs-own-job"
else echo "FAIL two-cap-runs-one-named-title-names-the-new-runs-own-job: the posted title is not 'CI job hit its time cap on main: build-guard'"; bad=1; fi
# A cap end whose commit has no pull request into main: its wake fails and names its run in the step summary. The other cap end
# still wakes, no issue is opened, the verdict is alarm, and the exit is non-zero.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/wake-nopr-5441 push 5441)" "$(gh_run ci cancelled 2026-01-01 https://runs/wake-withpr-5442 push 5442)"
jobs_of 5441 scope-guard:cancelled:40
jobs_of 5442 scope-guard:cancelled:40
workflow_at 5441 scope-guard:37
workflow_at 5442 scope-guard:37
wake_pulls_for 5441 '[]'
run_alarm "" "" "$tmp/summary"
cap_quiet cap-end-with-no-pr-exits-non-zero-with-verdict-alarm-and-no-issue nonzero
if grep -qF -- "cap:5441:1" "$tmp/summary"; then echo "ok   cap-end-with-no-pr-names-its-run-in-the-step-summary"
else echo "FAIL cap-end-with-no-pr-names-its-run-in-the-step-summary (summary: $(tr '\n' ' ' < "$tmp/summary"))"; bad=1; fi
wake_is cap-end-with-no-pr-the-other-cap-end-still-wakes 2 1 1
if grep -qF -- "<!-- main-alarm:cap:5442:1 -->" "$tmp/wakebodies"; then echo "ok   cap-end-with-no-pr-the-other-run-posts"
else echo "FAIL cap-end-with-no-pr-the-other-run-posts: no post names run 5442 ($(tr '\n' ' ' < "$tmp/wakebodies"))"; bad=1; fi
# One wake per cap-end run and attempt, each under its own KEY. A run whose attempt 1 is already named on the PR wakes for its
# attempt 2 cap end, and that wake names only attempt 2's cap jobs. The PR holds attempt 1's marker, so attempt 1 posts nothing.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/attempt-two-7040 push 7040 completed 2)"
attempt_jobs_of 7040 1 scope-guard:cancelled:40
jobs_of 7040 build-guard:cancelled:40
workflow_at 7040 scope-guard:37 build-guard:37
wake_comments_on 7 '[{"body": "<!-- main-alarm:cap:7040:1 -->\nalready woken"}]'
run_alarm
cap_quiet attempt-two-cap-end-after-attempt-one-was-named-is-alarm-with-no-issue zero
wake_is attempt-two-cap-end-reads-the-pr-per-attempt-and-posts-once 2 2 1
body_has attempt-two-wake-titles-its-own-first-job cap:7040:2 "CI job hit its time cap on main: build-guard"
body_has attempt-two-wake-names-its-own-cap-job cap:7040:2 "job build-guard ran 40 min, cap 37 min, run 7040"
body_has attempt-two-wake-names-no-attempt-one-job cap:7040:2 "!job scope-guard ran"
# The same run polled again: both attempts' markers are on the PR, so both wakes read it and neither posts.
wake_comments_on 7 '[{"body": "<!-- main-alarm:cap:7040:1 -->\nalready woken"}, {"body": "<!-- main-alarm:cap:7040:2 -->\nalready woken"}]'
run_alarm
cap_quiet attempt-two-cap-end-polled-with-both-markers-is-alarm-with-no-issue zero
wake_is attempt-two-cap-end-polled-with-both-markers-posts-nothing 2 2 0
# Two attempts, neither named yet: each attempt's cap end wakes the PR under its own KEY, one post per attempt.
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/two-attempts-7050 push 7050 completed 2)"
attempt_jobs_of 7050 1 scope-guard:cancelled:40
jobs_of 7050 build-guard:cancelled:40
workflow_at 7050 scope-guard:37 build-guard:37
wake_comments_on 7 '[]'
run_alarm
cap_quiet two-unreported-attempts-is-alarm-with-no-issue zero
wake_is two-unreported-attempts-each-post-their-own-wake 2 2 2
body_has two-unreported-attempts-attempt-one-wake-names-its-job cap:7050:1 "job scope-guard ran 40 min, cap 37 min, run 7050"
body_has two-unreported-attempts-attempt-one-wake-names-no-attempt-two-job cap:7050:1 "!job build-guard ran"
body_has two-unreported-attempts-attempt-two-wake-names-its-job cap:7050:2 "job build-guard ran 40 min, cap 37 min, run 7050"
# Control: a red run with no cap end opens its issue and makes no wake call.
runs_are "$(gh_run ci failure 2026-01-02 https://runs/wake-control-red-5450 push 5450)"
jobs_of 5450 checks:failure
t red control-red-run-without-a-cap-end-opens-its-issue "" "" "" "actions/runs/5450/jobs"
quiet_wake control-red-run-without-a-cap-end-makes-no-wake

# The scanner cases: a timeout-minutes line in a run block, a comment after the cap, a quoted timeout in a run line, a lone quote.
scanner_wf() {
  cat <<'YML'
name: ci
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20 # the cap
    steps:
      - name: "tool # not a comment"
        run: |
          echo "don't stop here"
          timeout-minutes: 1
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo "timeout-minutes: 2 # quoted"
YML
}
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/scan-quiet push 4721)"
jobs_of 4721 build:cancelled:15
scanner_wf | workflow_file 4721
t green scanner-a-run-block-timeout-line-is-not-the-cap "" "" ""
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/scan-red push 4722)"
jobs_of 4722 build:cancelled:20
scanner_wf | workflow_file 4722
t alarm scanner-a-comment-after-the-cap-is-stripped "" "" "$(capmsg 4722 build 20 20)" "actions/runs/4722/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/scan-unknown push 4723)"
jobs_of 4723 lint:cancelled:5
scanner_wf | workflow_file 4723
t green scanner-a-quoted-timeout-in-a-run-line-is-not-a-cap "" "" "" "actions/runs/4723/jobs"
# A job's quoted `name:` and quoted `timeout-minutes:` are read without their quotes (value()'s quote branch). The quoted name holds a
# `#`, which a comment strip would cut. Each case cancels its job at 40 minutes, against a cap of 37: the cap end names that job.
quoted_name_wf() {
  cat <<'YML'
name: ci
on: push
jobs:
  quoted:
    name: "Quoted #1"
    runs-on: ubuntu-latest
    timeout-minutes: 37
    steps:
      - run: echo ok
YML
}
quoted_cap_wf() {
  cat <<'YML'
name: ci
on: push
jobs:
  scope-guard:
    runs-on: ubuntu-latest
    timeout-minutes: '37'
    steps:
      - run: echo ok
YML
}
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/quoted-name-5010 push 5010)"
jobs_of 5010 "Quoted #1:cancelled:40"
quoted_name_wf | workflow_file 5010
t alarm job-with-a-quoted-name-is-named-by-its-name "" "" "$(capmsg 5010 'Quoted #1' 40 37)" "actions/runs/5010/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/quoted-cap-5011 push 5011)"
jobs_of 5011 scope-guard:cancelled:40
quoted_cap_wf | workflow_file 5011
t alarm job-with-a-single-quoted-cap-is-read-as-37 "" "" "$(capmsg 5011 scope-guard 40 37)" "actions/runs/5011/jobs"
runs_are "$(gh_run ci cancelled 2026-01-02 https://runs/quoted-cap-under-5012 push 5012)"
jobs_of 5012 scope-guard:cancelled:2
quoted_cap_wf | workflow_file 5012
t green job-with-a-single-quoted-cap-cancelled-under-its-cap-is-quiet "" "" ""

runs_are "$(gh_run ci success 2026-01-02 u1 schedule 2)" "$(gh_run ci failure 2026-01-01 u0 schedule 1)"
jobs_of 1 checks:failure
t green red-schedule-is-cleared-by-a-newer-green-schedule "" "" "" "actions/runs/1/jobs"
runs_are "$(gh_run ci success 2026-01-02 u1 workflow_dispatch 2)" "$(gh_run ci failure 2026-01-01 u0 push 1)"
jobs_of 1 checks:failure
jobs_of 2 checks:success
t green red-push-is-cleared-by-a-newer-green-dispatch "" "" "" "actions/runs/1/jobs actions/runs/2/jobs"
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
# The full-size cases read the repo's real checks.yml at the run's head. The step-level cap of checks-mutate-guard (5 minutes)
# sits under its job cap, so a 30-minute cancel is quiet, and the job cap is read past the comment on checks-guard.
mutate_cap="$(job_cap checks-mutate-guard)"
guard_cap="$(job_cap checks-guard)"
runs_are "$(gh_run checks cancelled 2026-01-02 https://runs/real-mutate push 4731)"
jobs_of 4731 checks-mutate-guard:cancelled:30
serve_real_checks "$(printf '%040x' 4731)"
if [ "${mutate_cap:-0}" -gt 30 ] 2>/dev/null; then echo "ok   real-checks-job-cap-is-above-the-30-minute-cancel"
else echo "FAIL real-checks-job-cap-is-above-the-30-minute-cancel (cap read: '$mutate_cap')"; bad=1; fi
t green real-checks-job-cap-is-read-past-a-step-cap "" "" ""
runs_are "$(gh_run checks cancelled 2026-01-02 https://runs/real-guard push 4732)"
jobs_of 4732 "checks-guard:cancelled:$guard_cap"
serve_real_checks "$(printf '%040x' 4732)"
t alarm real-checks-cap-with-a-trailing-comment-is-the-cap "" "" "$(capmsg 4732 checks-guard "$guard_cap" "$guard_cap")" "actions/runs/4732/jobs"
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
