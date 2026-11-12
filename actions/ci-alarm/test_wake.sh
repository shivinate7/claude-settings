#!/usr/bin/env bash
# Each c_ case runs by name through t, an indirect call that shellcheck cannot follow.
# shellcheck disable=SC2329
# Cases for actions/ci-alarm/wake.sh, the one home of a CI alarm on a push to main. The wake posts one
# comment on the merged pull request that produced the commit, holding the marker `<!-- main-alarm:KEY -->`.
# A repeat of KEY on that pull request posts nothing. Only a pull request merged into main counts, since the
# alarm is for a push to main. A commit with no such pull request opens no issue:
# the wake exits non-zero and says why.
#
# The fake gh (first on PATH in each run) serves three routes and logs each call to $CALLS, one line each:
#   pulls                 gh api repos/<repo>/commits/<sha>/pulls
#   comments <pr>         gh api repos/<repo>/issues/<pr>/comments
#   post <pr> <repo>      gh pr comment <pr> --repo <repo> --body <body>
#   other <args>          any other call, which fails
# A read is served from $PULLS/1 or $COMMENTS/<pr>/<page>. --paginate serves every page; without it, page 1.
# --jq applies to each page. A call that matches the glob $FAIL fails. The fake's own errors go to $FAKE_ERR,
# so the wake's stderr holds only the wake's own message.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
tmp="$work/case"; mkdir -p "$tmp/bin"

cat > "$tmp/bin/gh" <<'SH'
#!/usr/bin/env bash
route="" method=GET jqf="" paged="" prev="" body="" repo="" cls=""
for a in "$@"; do
  case "$a" in repos/*) [ -n "$route" ] || route="$a" ;; esac
  case "$prev" in
    --method|-X) method="$a" ;;
    --jq|-q) jqf="$a" ;;
    --body) body="$a" ;;
    --repo|-R) repo="$a" ;;
  esac
  [ "$a" = --paginate ] && paged=1
  prev="$a"
done
if [ "$1" = api ]; then
  case "$route" in
    */commits/*/pulls*) cls=pulls ;;
    */issues/*/comments*) n="${route#*/issues/}"; n="${n%%/*}"; cls="comments $n" ;;
  esac
  [ "$method" = GET ] || cls=""
elif [ "$1" = pr ] && [ "$2" = comment ]; then
  cls="post $3 $repo"
fi
[ -n "$cls" ] || cls="other $1 $2"
echo "$cls" >> "${CALLS:-/dev/null}"
if [ -n "${FAIL:-}" ] && [[ "$cls" == $FAIL ]]; then echo "gh: HTTP 500 (fake)" >> "${FAKE_ERR:-/dev/null}"; exit 1; fi
serve() {
  local dir="$1" k=1
  [ -f "$dir/1" ] || { echo "gh: no fixture in $dir (fake)" >> "${FAKE_ERR:-/dev/null}"; exit 1; }
  while [ -f "$dir/$k" ]; do
    if [ -n "$jqf" ]; then jq -r "$jqf" "$dir/$k" || exit 1; else cat "$dir/$k"; fi
    [ -n "$paged" ] || break
    k=$((k + 1))
  done
  exit 0
}
case "$cls" in
  pulls) serve "$PULLS" ;;
  comments\ *) serve "$COMMENTS/${cls#comments }" ;;
  post\ *) printf '%s\n' "$body" >> "${BODIES:-/dev/null}"; exit 0 ;;
esac
echo "gh: no route for $cls (fake)" >> "${FAKE_ERR:-/dev/null}"; exit 1
SH
chmod +x "$tmp/bin/gh"

SHA=0123456789abcdef0123456789abcdef01234567
ONE='[{"number": 7, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "main"}}]'
# The environment a case starts from. run_wake drops or overrides names here, and env -i keeps CI variables out.
DEF=(REPO=o/r "SHA=$SHA" KEY=run-42 "TEXT=CI alarm: main is red" GH_TOKEN=fake)
bad=0 why='' code='' out='' calls=''

# need <cause> <test...>: runs the test. When it fails, the case stops and <cause> is its one named cause.
need() { local cause="$1"; shift; "$@" || { why="$cause"; return 1; }; }

# pulls_are <json>: the pulls read of the commit serves this list.
pulls_are() { mkdir -p "$tmp/pulls"; printf '%s\n' "$1" > "$tmp/pulls/1"; }

# comments_on <pr> <json page>...: the comments of one pull request, one JSON array per page.
comments_on() {
  local pr="$1" k=1 page; shift
  mkdir -p "$tmp/comments/$pr"
  for page in "$@"; do printf '%s\n' "$page" > "$tmp/comments/$pr/$k"; k=$((k + 1)); done
}

# run_wake <name to leave out of DEF, or -> [VAR=value ...]: one run of the wake under a clean environment.
# Sets code (exit), out (stdout, also in $tmp/out), calls (the fake's log) and leaves stderr in $tmp/err.
run_wake() {
  local drop="$1" a name over=" " envs=()
  shift
  for a in "$@"; do over="$over${a%%=*} "; done
  for a in "${DEF[@]}"; do
    name="${a%%=*}"
    case "$over" in *" $name "*) continue ;; esac
    [ "$name" = "$drop" ] && continue
    envs+=("$a")
  done
  envs+=("$@")
  : > "$tmp/calls"; : > "$tmp/bodies"; : > "$tmp/summary"; : > "$tmp/err"; : > "$tmp/fake.err"
  out="$(env -i PATH="$tmp/bin:$PATH" CALLS="$tmp/calls" BODIES="$tmp/bodies" PULLS="$tmp/pulls" \
    COMMENTS="$tmp/comments" FAKE_ERR="$tmp/fake.err" "${envs[@]}" bash "$here/wake.sh" 2>"$tmp/err")"
  code=$?
  printf '%s\n' "$out" > "$tmp/out"
  calls="$(cat "$tmp/calls")"
}

n_post() { grep -c '^post' "$tmp/calls"; }
n_other() { grep -c '^other' "$tmp/calls"; }

# posted_on <pr> <KEY>: one pulls read, one comments read of pr, one post on pr of the repo, with the marker and TEXT.
posted_on() {
  need "the calls were not one pulls read, one comments read of PR $1 and one post on PR $1" \
    [ "$calls" = "$(printf 'pulls\ncomments %s\npost %s o/r' "$1" "$1")" ] &&
  need "the posted comment lacks the marker for KEY $2" grep -qF -- "<!-- main-alarm:$2 -->" "$tmp/bodies" &&
  need "the posted comment lacks the TEXT" grep -qF -- "CI alarm: main is red" "$tmp/bodies" &&
  need "exit was not 0 after a post" [ "$code" = 0 ]
}

# no_merged_pr_refused <file the message must be in>: a commit with no merged pull request reads its pulls,
# opens no issue and posts nothing, and the message names KEY and the first 7 characters of SHA.
no_merged_pr_refused() {
  need "the wake opened an issue or made another write" [ "$(n_other)" = 0 ] &&
  need "the wake posted a comment" [ "$(n_post)" = 0 ] &&
  need "the calls were not exactly one pulls read" [ "$calls" = pulls ] &&
  need "the message does not name KEY" grep -qF -- run-42 "$1" &&
  need "the message does not name the commit" grep -qF -- "${SHA:0:7}" "$1" &&
  need "exit was 0 for a commit with no merged pull request" [ "$code" != 0 ]
}

# names_failure <file the message must be in>: a failed read or post names KEY and says nobody was woken.
names_failure() {
  need "the failure message does not name KEY" grep -qF -- run-42 "$1" &&
  need "the failure message does not say nobody was woken" grep -qF -- "nobody was woken" "$1"
}

# Each case starts from empty fixtures; it sets the reads it expects, then runs the wake once.
c_fake_gh_control() {
  local gh="$tmp/bin/gh" x
  pulls_are "$ONE"; comments_on 7 '[{"body": "page one"}]' '[{"body": "page two"}]'
  : > "$tmp/calls"; : > "$tmp/bodies"
  CALLS="$tmp/calls" PULLS="$tmp/pulls" FAKE_ERR="$tmp/fake.err" "$gh" api "repos/o/r/commits/$SHA/pulls" >/dev/null
  x="$(CALLS="$tmp/calls" COMMENTS="$tmp/comments" FAKE_ERR="$tmp/fake.err" "$gh" api --paginate \
    "repos/o/r/issues/7/comments?per_page=100" --jq '.[].body')"
  CALLS="$tmp/calls" BODIES="$tmp/bodies" FAKE_ERR="$tmp/fake.err" "$gh" pr comment 7 --repo o/r --body 'a comment' >/dev/null
  calls="$(cat "$tmp/calls")"
  need "the fake's paginated comments read did not serve both pages" [ "$x" = "$(printf 'page one\npage two')" ] &&
  need "the fake did not log one pulls read, one comments read and one post on PR 7" \
    [ "$calls" = "$(printf 'pulls\ncomments 7\npost 7 o/r')" ]
}

c_one_merged_pr() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake -
  posted_on 7 run-42
}

c_same_key_repeat_skips() {
  pulls_are "$ONE"; comments_on 7 '[{"body": "<!-- main-alarm:run-42 -->\nalready posted"}]'
  run_wake -
  need "the wake did not read PR 7's comments once after its one pulls read" [ "$calls" = "$(printf 'pulls\ncomments 7')" ] &&
  need "a repeat of KEY run-42 posted again" [ "$(n_post)" = 0 ] &&
  need "exit was not 0 on a repeat" [ "$code" = 0 ]
}

# The marker is on page two, so a read of page one alone would post a second comment.
c_same_key_repeat_on_page_two_skips() {
  local full
  full="$(jq -cn '[range(30) | {body: "unrelated comment \(.)"}]')"
  pulls_are "$ONE"; comments_on 7 "$full" '[{"body": "<!-- main-alarm:run-42 -->\nalready posted"}]'
  run_wake -
  need "the wake did not read PR 7's comments once after its one pulls read" [ "$calls" = "$(printf 'pulls\ncomments 7')" ] &&
  need "a repeat posted again: the marker on comments page two was not read" [ "$(n_post)" = 0 ] &&
  need "exit was not 0 on a repeat" [ "$code" = 0 ]
}

c_key_a_is_not_matched_by_a_b() {
  pulls_are "$ONE"; comments_on 7 '[{"body": "<!-- main-alarm:a-b -->\nearlier"}]'
  run_wake - KEY=a
  posted_on 7 a
}

c_other_key_on_pr_posts() {
  pulls_are "$ONE"; comments_on 7 '[{"body": "<!-- main-alarm:other-run -->\nearlier"}]'
  run_wake -
  posted_on 7 run-42
}

c_no_merged_pr_names_key_and_sha_in_summary() {
  pulls_are '[]'
  run_wake - "GITHUB_STEP_SUMMARY=$tmp/summary"
  no_merged_pr_refused "$tmp/summary"
}

c_no_merged_pr_names_key_and_sha_on_stderr() {
  pulls_are '[]'
  run_wake -
  no_merged_pr_refused "$tmp/err"
}

c_only_unmerged_pr_is_refused_like_no_pr() {
  pulls_are '[{"number": 8, "merged_at": null, "base": {"ref": "main"}}]'
  run_wake - "GITHUB_STEP_SUMMARY=$tmp/summary"
  no_merged_pr_refused "$tmp/summary"
}

c_unmerged_and_merged_pr_posts_on_merged() {
  pulls_are '[{"number": 8, "merged_at": null, "base": {"ref": "main"}}, {"number": 7, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "main"}}]'
  comments_on 7 '[]'
  run_wake -
  posted_on 7 run-42
}

# The later merge comes first in the list, so a read of the first entry would pick PR 9.
c_two_merged_prs_posts_on_earliest() {
  pulls_are '[{"number": 9, "merged_at": "2026-11-12T13:00:00Z", "base": {"ref": "main"}}, {"number": 7, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "main"}}]'
  comments_on 7 '[]'
  run_wake -
  posted_on 7 run-42
}

# The batch merge came first, so a pick by merge time alone takes PR 1: the base filter must skip it.
c_main_merge_wins_over_an_earlier_batch_merge() {
  pulls_are '[{"number": 2, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "main"}}, {"number": 1, "merged_at": "2026-11-12T11:00:00Z", "base": {"ref": "batch-103"}}]'
  comments_on 2 '[]'
  comments_on 1 '[]'
  run_wake -
  posted_on 2 run-42
}

# A merge into another branch is not the pull request that put the commit on main.
c_only_batch_merge_is_refused_like_no_pr() {
  pulls_are '[{"number": 7, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "batch-103"}}]'
  comments_on 7 '[]'
  run_wake - "GITHUB_STEP_SUMMARY=$tmp/summary"
  no_merged_pr_refused "$tmp/summary"
}

c_main_unmerged_and_batch_merge_is_refused_like_no_pr() {
  pulls_are '[{"number": 8, "merged_at": null, "base": {"ref": "main"}}, {"number": 7, "merged_at": "2026-11-12T12:00:00Z", "base": {"ref": "batch-103"}}]'
  comments_on 7 '[]'
  run_wake - "GITHUB_STEP_SUMMARY=$tmp/summary"
  no_merged_pr_refused "$tmp/summary"
}

c_pulls_read_fails_is_loud_and_posts_nothing() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake - "FAIL=pulls"
  need "the calls were not exactly one pulls read, then nothing" [ "$calls" = pulls ] &&
  names_failure "$tmp/err" &&
  need "exit was 0 after a failed pulls read" [ "$code" != 0 ]
}

c_comments_read_fails_is_loud_and_posts_nothing() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake - "FAIL=comments 7"
  need "the calls were not one pulls read then one failed comments read of PR 7" [ "$calls" = "$(printf 'pulls\ncomments 7')" ] &&
  need "a comments read that failed was followed by a post" [ "$(n_post)" = 0 ] &&
  names_failure "$tmp/err" &&
  need "exit was 0 after a failed comments read" [ "$code" != 0 ]
}

c_failed_post_is_loud() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake - "FAIL=post*"
  need "the calls were not one pulls read, one comments read and one post attempt on PR 7" \
    [ "$calls" = "$(printf 'pulls\ncomments 7\npost 7 o/r')" ] &&
  names_failure "$tmp/err" &&
  need "exit was 0 after a failed post" [ "$code" != 0 ]
}

c_dry_run_prints_body_and_posts_nothing() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake - WAKE_DRY=1
  need "the dry run made a post call" [ "$(n_post)" = 0 ] &&
  need "the dry run's output lacks the marker for KEY run-42" grep -qF -- "<!-- main-alarm:run-42 -->" "$tmp/out" &&
  need "the dry run's output lacks the TEXT" grep -qF -- "CI alarm: main is red" "$tmp/out" &&
  need "exit was not 0 on a dry run" [ "$code" = 0 ]
}

# c_missing_var <VAR>: the run with VAR unset is refused, names VAR on stderr, and posts nothing.
c_missing_var() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake "$1"
  need "a run with $1 unset posted a comment" [ "$(n_post)" = 0 ] &&
  need "the refusal does not name $1" grep -qw -- "$1" "$tmp/err" &&
  need "exit was 0 with $1 unset" [ "$code" != 0 ]
}

# c_refuses_key <KEY value>: a KEY with a quote, a `-->`, or a newline is refused by name and posts nothing.
c_refuses_key() {
  pulls_are "$ONE"; comments_on 7 '[]'
  run_wake - "KEY=$1"
  need "a refused KEY posted a comment" [ "$(n_post)" = 0 ] &&
  need "the refusal does not name KEY" grep -qw -- KEY "$tmp/err" &&
  need "exit was 0 for a refused KEY" [ "$code" != 0 ]
}

# Each case runs on fresh fixtures and prints one line: ok, or FAIL with its one named cause.
t() {
  local name="$1" fn="$2"; shift 2
  why=""; rm -rf "$tmp/pulls" "$tmp/comments"
  if "$fn" "$@"; then echo "ok   $name"
  else echo "FAIL $name: $why (exit $code; calls: $(tr '\n' ' ' < "$tmp/calls"))"; bad=1; fi
}

t "control: the fake gh serves pages and logs each call" c_fake_gh_control
t "one merged PR: one comment on it, with the marker and TEXT" c_one_merged_pr
t "same KEY already on the PR: no post, exit 0" c_same_key_repeat_skips
t "same KEY on comments page two: no post (every page is read)" c_same_key_repeat_on_page_two_skips
t "KEY a is not matched by the marker of KEY a-b" c_key_a_is_not_matched_by_a_b
t "a different KEY on the PR: posts" c_other_key_on_pr_posts
t "no PR: refused, names KEY and SHA in the step summary, opens no issue" c_no_merged_pr_names_key_and_sha_in_summary
t "no PR: refused, names KEY and SHA on stderr, opens no issue" c_no_merged_pr_names_key_and_sha_on_stderr
t "only an unmerged PR: refused like no PR" c_only_unmerged_pr_is_refused_like_no_pr
t "one unmerged and one merged PR: comment on the merged one" c_unmerged_and_merged_pr_posts_on_merged
t "two merged PRs: comment on the earliest merged" c_two_merged_prs_posts_on_earliest
t "a merge into batch-103 before the main merge: comment on the main merge" c_main_merge_wins_over_an_earlier_batch_merge
t "only a merge into batch-103: refused like no PR, names KEY and SHA in the step summary" c_only_batch_merge_is_refused_like_no_pr
t "a main PR unmerged and a merge into batch-103: refused like no PR" c_main_unmerged_and_batch_merge_is_refused_like_no_pr
t "pulls read fails: exit non-zero with a message, no post" c_pulls_read_fails_is_loud_and_posts_nothing
t "comments read fails: exit non-zero with a message, no post" c_comments_read_fails_is_loud_and_posts_nothing
t "failed post: exit non-zero with a message" c_failed_post_is_loud
t "WAKE_DRY=1: prints the body, no post" c_dry_run_prints_body_and_posts_nothing
t "REPO unset: refused naming REPO" c_missing_var REPO
t "SHA unset: refused naming SHA" c_missing_var SHA
t "KEY unset: refused naming KEY" c_missing_var KEY
t "TEXT unset: refused naming TEXT" c_missing_var TEXT
t "KEY with a double quote: refused, no post" c_refuses_key 'a"b'
t "KEY with a single quote: refused, no post" c_refuses_key "a'b"
t "KEY with --> : refused, no post" c_refuses_key 'a-->b'
t "KEY with a newline: refused, no post" c_refuses_key "$(printf 'a\nb')"

exit $bad
