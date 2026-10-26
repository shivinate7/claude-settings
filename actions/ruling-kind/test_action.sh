#!/usr/bin/env bash
# Red and green proof for actions/ruling-kind. Each case builds a fixture repo (a bare remote,
# main, and topic branches) and runs check.sh inside it, as action.yml does.
#  - declared-record-passes: the topic diff holds only the declared record. A pass alone proves
#    nothing (a lint that read no records also passes), so two sub-checks follow it:
#    action-repo-record-ignored (an undeclared record only in the action's own repo must not
#    change the run) and caller-root-record-read (an undeclared record in the caller root must
#    go red and be named). A lint that ignored --root fails both.
#  - develop-base-declared-passes: BASE_REF=develop. A check.sh that drops --base diffs main,
#    finds the develop-only undeclared record, and goes red.
#  - unpersisted-local-base-passes: origin/main is present locally and origin is unreachable.
#    The run uses the local ref and passes. A check.sh that fetches first goes red.
#  - shallow-no-merge-base-red: a depth-1 clone with no merge base is red, with the lint's
#    message. It is never a silent green.
#  - action-only-rule-passes, caller-only-rule-passes, neither-rule-fails: a rule Home resolves
#    against the action's CLAUDE.md or the caller's, and fails in neither.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
TRACKED_ROOT="$(cd "$here/../.." && pwd)"
# shellcheck source=../../testing/tracked_tree.sh
. "$TRACKED_ROOT/testing/tracked_tree.sh"  # copies what git lists, so no fixture lists files
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
record develop decisions/develop-undeclared.md 'No kind line here.\n'
record develop-topic decisions/develop-declared.md 'Kind: process\nHome: fixture-home.md\n' develop
quiet git clone -q -b topic "$remote" "$tmp/topic"
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
mkdir -p "$act/actions/ruling-kind"
quiet cp "$here/check.sh" "$act/actions/ruling-kind/"
quiet copy_tracked "$act" lint hooks  # the lint, the layout check.sh reads, and their imports
quiet git -C "$act" switch -q -c action-only
mkdir -p "$act/decisions"; printf 'No kind line here.\n' > "$act/decisions/action-only.md"
quiet git -C "$act" add decisions/action-only.md
quiet git -C "$act" commit -q -m action-only
expect 0 action-repo-record-ignored "$tmp/topic" main "" "$act/actions/ruling-kind/check.sh"
# The same caller root, with one undeclared record committed: red, and the lint names it.
mkdir -p "$tmp/topic/decisions"; printf 'No kind line here.\n' > "$tmp/topic/decisions/second-undeclared.md"
quiet git -C "$tmp/topic" add decisions/second-undeclared.md
quiet git -C "$tmp/topic" commit -q -m second-undeclared
# The --root proof: a lint that ignored --root would diff the action's repo and pass.
expect 1 caller-root-record-read "$tmp/topic" main "FAIL: decisions/second-undeclared.md"
expect 1 unreadable-base-fails "$tmp/topic" no-such-base "cannot fetch base"
expect 0 empty-base-skipped "$tmp/topic" "" "skipped"
expect 0 develop-base-declared-passes "$tmp/develop" develop ""
# origin/main is already local; the remote is gone. The run must use the local ref.
quiet git -C "$tmp/unpersisted" rev-parse --verify -q origin/main
quiet git -C "$tmp/unpersisted" remote set-url origin "$tmp/unreachable.git"
expect 0 unpersisted-local-base-passes "$tmp/unpersisted" main ""
expect 1 shallow-no-merge-base-red "$tmp/shallow" main "git diff failed"
# A Home: rule:<id> resolves against the action's own CLAUDE.md and the caller's. The action root
# is a copy of check.sh and the lint, with its own CLAUDE.md (one rule). Each caller clone adds one
# declared record, and maybe a CLAUDE.md with one rule of its own.
actroot="$tmp/actroot"
mkdir -p "$actroot/actions/ruling-kind"
quiet cp "$here/check.sh" "$actroot/actions/ruling-kind/"
quiet copy_tracked "$actroot" lint hooks  # the lint, the layout check.sh reads, and their imports
printf '# Action rules\n\nRule text. <!-- rule:action-rule -->\n' > "$actroot/CLAUDE.md"
# Case 1: the rule lives only in the action's CLAUDE.md. The caller has no CLAUDE.md.
quiet git clone -q "$remote" "$tmp/rule-action"
quiet git -C "$tmp/rule-action" switch -q -c rule-action
mkdir -p "$tmp/rule-action/decisions"
printf 'Kind: process\nHome: rule:action-rule\n' > "$tmp/rule-action/decisions/action-only.md"
quiet git -C "$tmp/rule-action" add -A
quiet git -C "$tmp/rule-action" commit -q -m rule-action
expect 0 action-only-rule-passes "$tmp/rule-action" main "" "$actroot/actions/ruling-kind/check.sh"
# Case 2: the rule lives only in the caller's CLAUDE.md.
quiet git clone -q "$remote" "$tmp/rule-caller"
quiet git -C "$tmp/rule-caller" switch -q -c rule-caller
mkdir -p "$tmp/rule-caller/decisions"
printf 'Kind: process\nHome: rule:caller-rule\n' > "$tmp/rule-caller/decisions/caller-only.md"
printf '# Caller rules\n\nRule text. <!-- rule:caller-rule -->\n' > "$tmp/rule-caller/CLAUDE.md"
quiet git -C "$tmp/rule-caller" add -A
quiet git -C "$tmp/rule-caller" commit -q -m rule-caller
expect 0 caller-only-rule-passes "$tmp/rule-caller" main "" "$actroot/actions/ruling-kind/check.sh"
# Case 3: the rule lives in neither CLAUDE.md. Red, and the lint names the Home.
quiet git clone -q "$remote" "$tmp/rule-none"
quiet git -C "$tmp/rule-none" switch -q -c rule-none
mkdir -p "$tmp/rule-none/decisions"
printf 'Kind: process\nHome: rule:no-such-rule\n' > "$tmp/rule-none/decisions/neither-rule.md"
quiet git -C "$tmp/rule-none" add -A
quiet git -C "$tmp/rule-none" commit -q -m rule-none
expect 1 neither-rule-fails "$tmp/rule-none" main "Home rule:no-such-rule is not a rule marker" "$actroot/actions/ruling-kind/check.sh"
exit $bad
