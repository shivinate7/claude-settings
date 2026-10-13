#!/usr/bin/env bash
# Red and green proof for actions/ruling-kind. Each case builds a fixture repo (a bare remote,
# main, and topic branches) and runs check.sh inside it, as action.yml does.
#  - declared-record-passes: the topic diff holds only the declared record. A pass alone proves
#    nothing (a lint that read no records also passes), so two sub-checks follow it:
#    action-repo-record-ignored (an undeclared record only in the action's own repo must not
#    change the run) and caller-root-record-read (an undeclared record in the caller root must
#    go red and be named). A lint that ignored --root fails both.
#  - undeclared-record-fails: the --root proof from before. A lint that ignored --root would
#    diff the action's repo, find no bad record, and pass.
#  - develop-base-declared-passes: BASE_REF=develop. A check.sh that drops --base diffs main,
#    finds the develop-only undeclared record, and goes red.
#  - unpersisted-local-base-passes: origin/main is present locally and origin is unreachable.
#    The run uses the local ref and passes. A check.sh that fetches first goes red.
#  - shallow-no-merge-base-red: a depth-1 clone with no merge base is red, with the lint's
#    message. It is never a silent green.
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
record() { # branch file body [from-branch]: a branch that adds one record (default from main)
  quiet git -C "$seed" switch -q -c "$1" "${4:-main}"
  mkdir -p "$seed/$(dirname "$2")"; printf '%b' "$3" > "$seed/$2"
  quiet git -C "$seed" add "$2"
  quiet git -C "$seed" commit -q -m "$1"
  quiet git -C "$seed" push -q "$remote" "$1"
}
record topic decisions/declared-ruling.md 'Kind: process\nHome: fixture-home.md\n'
record topic-undeclared decisions/undeclared-ruling.md 'No kind line here.\n'
record develop decisions/develop-undeclared.md 'No kind line here.\n'
record develop-topic decisions/develop-declared.md 'Kind: process\nHome: fixture-home.md\n' develop
quiet git clone -q -b topic "$remote" "$tmp/topic"
quiet git clone -q -b topic-undeclared "$remote" "$tmp/undeclared"
quiet git clone -q -b develop-topic "$remote" "$tmp/develop"
quiet git clone -q -b topic "$remote" "$tmp/unpersisted"
quiet git clone -q --no-local --depth 1 -b topic "$remote" "$tmp/shallow"
[ "$(git -C "$tmp/shallow" rev-parse --is-shallow-repository)" = true ] ||
  { echo "fixture setup failed: the shallow clone is not shallow"; exit 1; }
bad=0
expect() { # want-exit label work-dir base-ref want-text (empty: no text check) [check.sh]
  out="$(cd "$3" && BASE_REF="$4" bash "${6:-$here/check.sh}" 2>&1)"; got=$?
  if [ "$got" -eq "$1" ] && { [ -z "$5" ] || printf '%s' "$out" | grep -q -F -- "$5"; }; then echo "ok   $2"
  else echo "FAIL $2 (exit $got, wanted $1)"; printf '%s\n' "$out" | sed 's/^/     /'; bad=1; fi
}
only="$(git -C "$tmp/topic" diff --name-only origin/main...HEAD -- decisions)"
[ "$only" = "decisions/declared-ruling.md" ] ||
  { echo "fixture setup failed: the topic must add only the declared record, found: $only"; exit 1; }
expect 0 declared-record-passes "$tmp/topic" main ""
# The action's own repo: a clone with a copy of check.sh and the lint. Its record is never the caller's.
act="$tmp/action"
quiet git clone -q "$remote" "$act"
mkdir -p "$act/actions/ruling-kind" "$act/lint"
quiet cp "$here/check.sh" "$act/actions/ruling-kind/"
quiet cp "$here/../../lint/check_ruling_kind.py" "$act/lint/"
quiet git -C "$act" switch -q -c action-only
mkdir -p "$act/decisions"; printf 'No kind line here.\n' > "$act/decisions/action-only.md"
quiet git -C "$act" add decisions/action-only.md
quiet git -C "$act" commit -q -m action-only
expect 0 action-repo-record-ignored "$tmp/topic" main "" "$act/actions/ruling-kind/check.sh"
# The same caller root, with one undeclared record committed: red, and the lint names it.
mkdir -p "$tmp/topic/decisions"; printf 'No kind line here.\n' > "$tmp/topic/decisions/second-undeclared.md"
quiet git -C "$tmp/topic" add decisions/second-undeclared.md
quiet git -C "$tmp/topic" commit -q -m second-undeclared
expect 1 caller-root-record-read "$tmp/topic" main "FAIL: decisions/second-undeclared.md"
expect 1 undeclared-record-fails "$tmp/undeclared" main "check_ruling_kind: FAIL"
expect 1 unreadable-base-fails "$tmp/topic" no-such-base "cannot fetch base"
expect 0 empty-base-skipped "$tmp/topic" "" "skipped"
expect 0 develop-base-declared-passes "$tmp/develop" develop ""
# origin/main is already local; the remote is gone. The run must use the local ref.
quiet git -C "$tmp/unpersisted" rev-parse --verify -q origin/main
quiet git -C "$tmp/unpersisted" remote set-url origin "$tmp/unreachable.git"
expect 0 unpersisted-local-base-passes "$tmp/unpersisted" main ""
expect 1 shallow-no-merge-base-red "$tmp/shallow" main "git diff failed"
exit $bad
