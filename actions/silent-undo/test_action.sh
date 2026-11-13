#!/usr/bin/env bash
# Red and green runs for actions/silent-undo. Each case builds a fixture repo (a bare remote, main
# with commit A then commit B changing rules.md, and topic branches cut from main's tip) and runs
# check.sh inside it, as action.yml runs it with BASE_REF and HEAD_SHA set.
#  - revert-to-main-red: the topic puts rules.md back to its content before B (the reversal read).
#    check.sh exits 1 and names the file.
#  - clean-branch-green: the topic adds one unrelated file. With the revert case, this pair shows
#    the check reads the topic and does not fail every branch.
#  - empty-branch-green: a branch with no commit of its own sits at main's tip. Nothing lands.
#  - trailer-excuses-green: the same revert with `Drops-lines: rules.md -- <reason>` passes and
#    prints ALLOWED for the file.
#  - trailer-without-reason-red, trailer-other-path-red: a trailer with no reason, or one for
#    another path, excuses nothing.
#  - no-base-skipped: BASE_REF empty (no pull request) exits 0 with a skip message. The fixture
#    holds the revert, so a green here comes from the skip, not from a clean diff.
#  - pr-head-sha-read-red: the checkout sits at main and HEAD_SHA names the revert. check.sh reads
#    HEAD_SHA (the pull request head), not the checkout's HEAD, so it goes red.
#  - unreadable-base-red: a base that cannot be fetched is UNKNOWN, exit 1, never green.
#  - unpersisted-local-base-red: origin/main is local and origin is unreachable. The run uses the
#    local ref and names the file. A check.sh that fetches first goes UNKNOWN.
#  - shallow-unknown-red: a depth-1 clone is UNKNOWN, exit 1.
#  - single-branch-fetches-base: a single-branch clone of topic-revert holds no origin/main. check.sh
#    fetches the base and reads the real verdict, exit 1 and the file named.
# Without a check.sh every case fails with "not built": that is the red on the old code.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
check="$here/check.sh"
# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT
. "$root/lint/_test_git.sh"  # test-run signing opt-out
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
quiet() { # run a fixture step; keep its output, stop the suite if the fixture cannot be built
  out="$("$@" 2>&1)" || { echo "fixture setup failed: $*"; echo "$out"; exit 1; }
}
A='rule one\nrule two\n'
B='rule one\nrule two, reworded\nrule three\n'
remote="$work/remote.git"; seed="$work/seed"
quiet git init -q -b main "$seed"
printf '%b' "$A" > "$seed/rules.md"
quiet git -C "$seed" add rules.md
quiet git -C "$seed" commit -q -m "A: add the rules"
printf '%b' "$B" > "$seed/rules.md"
quiet git -C "$seed" add rules.md
quiet git -C "$seed" commit -q -m "B: reword the rules"
quiet git init -q --bare -b main "$remote"
quiet git -C "$seed" push -q "$remote" main
branch() { # name file content message: a commit on a new branch cut from main's tip, pushed to the remote
  quiet git -C "$seed" switch -q -c "$1" main
  mkdir -p "$seed/$(dirname "$2")"; printf '%b' "$3" > "$seed/$2"
  quiet git -C "$seed" add -- "$2"
  printf '%b\n' "$4" > "$work/message"
  quiet git -C "$seed" commit -q -F "$work/message"
  quiet git -C "$seed" push -q "$remote" "$1"
}
branch topic-revert rules.md "$A" 'restore the rules file'
branch topic-clean notes/unrelated.txt 'an unrelated note\n' 'add an unrelated note'
branch topic-trailer rules.md "$A" 'restore the rules file on purpose\n\nDrops-lines: rules.md -- the rules are rolled back on purpose for this test'
branch topic-noreason rules.md "$A" 'restore the rules file\n\nDrops-lines: rules.md'
branch topic-otherpath rules.md "$A" 'restore the rules file\n\nDrops-lines: other.md -- a reason for a file that did not change'
quiet git -C "$seed" push -q "$remote" main:topic-empty
quiet git clone -q -b topic-revert "$remote" "$work/revert"
quiet git clone -q -b topic-revert "$remote" "$work/unpersisted"
quiet git clone -q -b topic-clean "$remote" "$work/clean"
quiet git clone -q -b topic-empty "$remote" "$work/empty"
quiet git clone -q -b topic-trailer "$remote" "$work/trailer"
quiet git clone -q -b topic-noreason "$remote" "$work/noreason"
quiet git clone -q -b topic-otherpath "$remote" "$work/otherpath"
quiet git clone -q -b main "$remote" "$work/base"
quiet git clone -q --no-local --depth 1 -b topic-revert "$remote" "$work/shallow"
quiet git clone -q --single-branch -b topic-revert "$remote" "$work/single"
# The fixture must hold what each case claims, or the verdicts below prove nothing.
[ "$(git -C "$work/revert" diff --name-only origin/main...HEAD)" = rules.md ] ||
  { echo "fixture setup failed: topic-revert must change only rules.md"; exit 1; }
[ "$(git -C "$work/revert" show HEAD:rules.md)" = "$(printf '%b' "$A")" ] ||
  { echo "fixture setup failed: topic-revert must put rules.md back to commit A's content"; exit 1; }
[ "$(git -C "$work/clean" diff --name-only origin/main...HEAD)" = notes/unrelated.txt ] ||
  { echo "fixture setup failed: topic-clean must add only the unrelated note"; exit 1; }
[ "$(git -C "$work/empty" rev-list --count origin/main..HEAD)" = 0 ] ||
  { echo "fixture setup failed: topic-empty must hold no commit of its own"; exit 1; }
[ "$(git -C "$work/shallow" rev-parse --is-shallow-repository)" = true ] ||
  { echo "fixture setup failed: the shallow clone is not shallow"; exit 1; }
[ -n "$(git -C "$work/unpersisted" rev-parse --verify -q origin/main)" ] ||
  { echo "fixture setup failed: the unpersisted clone has no local origin/main"; exit 1; }
[ -z "$(git -C "$work/single" rev-parse --verify -q refs/remotes/origin/main)" ] ||
  { echo "fixture setup failed: the single-branch clone holds origin/main, so the base fetch is not exercised"; exit 1; }
quiet git -C "$work/unpersisted" remote set-url origin "$work/unreachable.git"
head_rev="$(git -C "$work/revert" rev-parse HEAD)"
fails=0
expect() { # label want-exit work-dir base-ref want-text [head-sha] [pr-body]: runs check.sh as action.yml does
  label=$1 want=$2 dir=$3 base=$4 text=$5 head=${6:-$(git -C "$3" rev-parse HEAD)} body=${7-}
  if [ ! -f "$check" ]; then echo "FAIL $label: check.sh is not built at $check"; fails=$((fails + 1)); return; fi
  # A pr-body goes in the event file that CI gives the step (GITHUB_EVENT_PATH), never in the step's env.
  envset=()
  if [ -n "$body" ]; then
    event="$work/event-$label.json"
    python3 -I -c 'import json, sys
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump({"pull_request": {"body": sys.argv[1]}}, f)' "$body" "$event" || { echo "fixture setup failed: the event file of $label"; exit 1; }
    envset=("GITHUB_EVENT_PATH=$event")
  fi
  # env -u CI: GitHub sets CI, which makes the lint red on UNKNOWN even without --strict. The cases must test --strict itself.
  # env -u GITHUB_EVENT_PATH: a run on CI has the live event file; no case may read the live pull request body.
  out="$(cd "$dir" && env -u CI -u GITHUB_EVENT_PATH ${envset[@]+"${envset[@]}"} BASE_REF="$base" HEAD_SHA="$head" bash "$check" 2>&1)"; got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL $label: exit $got, wanted $want"; printf '%s\n' "$out" | sed 's/^/     /'; fails=$((fails + 1))
  elif [ -n "$text" ] && ! printf '%s' "$out" | grep -q -F -- "$text"; then
    echo "FAIL $label: output lacks '$text'"; printf '%s\n' "$out" | sed 's/^/     /'; fails=$((fails + 1))
  else echo "ok   $label"; fi
}
expect revert-to-main-red 1 "$work/revert" main "FAIL: rules.md"
expect clean-branch-green 0 "$work/clean" main ""
expect empty-branch-green 0 "$work/empty" main ""
expect trailer-excuses-green 0 "$work/trailer" main "ALLOWED rules.md"
expect trailer-without-reason-red 1 "$work/noreason" main "FAIL: rules.md"
expect trailer-other-path-red 1 "$work/otherpath" main "FAIL: rules.md"
expect no-base-skipped 0 "$work/revert" "" "skipped"
expect pr-head-sha-read-red 1 "$work/base" main "FAIL: rules.md" "$head_rev"
expect unreadable-base-red 1 "$work/revert" no-such-base "UNKNOWN"
expect unpersisted-local-base-red 1 "$work/unpersisted" main "FAIL: rules.md"
expect shallow-unknown-red 1 "$work/shallow" main "UNKNOWN"
expect single-branch-fetches-base 1 "$work/single" main "FAIL: rules.md"
# The pull request body, in the event file CI gives the step, excuses its path the way a commit trailer does.
expect body-excuse-green 0 "$work/revert" main "ALLOWED rules.md" "" $'Summary.\n\nDrops-lines: rules.md -- the rules are rolled back on purpose for this test'
echo "silent-undo suite: $fails failed"
exit $((fails > 0))
