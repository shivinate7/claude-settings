#!/usr/bin/env bash
# Red and green proof for actions/ruling-kind. Each case builds a fixture repo (a bare remote,
# main, topic) and runs check.sh inside it, as action.yml does. Case 2 is the --root proof: a
# lint that ignored --root would diff this repo, find no bad record, and pass.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
quiet() { # run a fixture step; keep its output, stop the suite if the fixture cannot be built
  out="$("$@" 2>&1)" || { echo "fixture setup failed: $*"; echo "$out"; exit 1; }
}
remote="$tmp/remote.git"; seed="$tmp/seed"
quiet git init -q -b main "$seed"
echo 'Home for the fixture ruling.' > "$seed/fixture-home.md"
quiet git -C "$seed" add fixture-home.md
quiet git -C "$seed" commit -q -m main
quiet git init -q --bare -b main "$remote"
quiet git -C "$seed" push -q "$remote" main
record() { # branch file body: a branch from main that adds one record
  quiet git -C "$seed" switch -q -c "$1" main
  mkdir -p "$seed/$(dirname "$2")"; printf '%b' "$3" > "$seed/$2"
  quiet git -C "$seed" add "$2"
  quiet git -C "$seed" commit -q -m "$1"
  quiet git -C "$seed" push -q "$remote" "$1"
}
record topic decisions/declared-ruling.md 'Kind: process\nHome: fixture-home.md\n'
record topic-undeclared decisions/undeclared-ruling.md 'No kind line here.\n'
quiet git clone -q -b topic "$remote" "$tmp/topic"
quiet git clone -q -b topic-undeclared "$remote" "$tmp/undeclared"
bad=0
expect() { # want-exit label work-dir base-ref want-text (empty: no text check)
  out="$(cd "$3" && BASE_REF="$4" bash "$here/check.sh" 2>&1)"; got=$?
  if [ "$got" -eq "$1" ] && { [ -z "$5" ] || printf '%s' "$out" | grep -q -F -- "$5"; }; then echo "ok   $2"
  else echo "FAIL $2 (exit $got, wanted $1)"; printf '%s\n' "$out" | sed 's/^/     /'; bad=1; fi
}
expect 0 declared-record-passes "$tmp/topic" main ""
expect 1 undeclared-record-fails "$tmp/undeclared" main "check_ruling_kind: FAIL"
expect 1 unreadable-base-fails "$tmp/topic" no-such-base "cannot fetch base"
expect 0 empty-base-skipped "$tmp/topic" "" "skipped"
exit $bad
