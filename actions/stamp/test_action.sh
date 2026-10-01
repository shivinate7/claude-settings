#!/usr/bin/env bash
# Runnable self-test for run.sh (the composite action's own logic), against a real throwaway
# git remote. `bash actions/stamp/test_action.sh`. No framework: each test is a function: it
# prints "ok - <name>" and returns 0, or prints "FAIL - <name>" with the reason and returns 1.
set -uo pipefail

# A CI run's own refs name the runner's branch, not a fixture's. GITHUB_ACTIONS picks a hard
# refusal or an UNKNOWN line for an unreadable base, so each test that reads one sets it itself.
unset GITHUB_REF GITHUB_BASE_REF GITHUB_ACTIONS MODE BASE

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$HERE/run.sh"
STAMP_JS="$HERE/stamp.mjs"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

failed=0
total=0

run_test() {
  local name="$1"
  total=$((total + 1))
  if "$2"; then
    echo "ok - $name"
  else
    echo "FAIL - $name"
    failed=$((failed + 1))
  fi
}

write_config() {
  local dir="$1"
  cat > "$dir/stamp.json" <<'JSON'
{
  "defaultBranch": "main",
  "kinds": [
    {
      "id": "decision",
      "folder": "docs/decisions",
      "prefix": "D",
      "pad": 3,
      "idTemplate": "{prefix}-{n}",
      "pendingRegex": "^id:[ \\t]*pending[ \\t]*$",
      "order": "merge"
    }
  ]
}
JSON
}

new_bare_remote() {
  local remote="$WORK/remote-$RANDOM"
  git init -q --bare -b main "$remote" >/dev/null
  echo "$remote"
}

clone_with_pending_record() {
  local remote="$1"
  local local_dir="$WORK/local-$RANDOM"
  git clone -q "$remote" "$local_dir" >/dev/null 2>/dev/null # cloning an empty bare repo warns; harmless
  (
    cd "$local_dir" || exit 1
    git config user.email test@example.com
    git config user.name test
    git config core.autocrlf false
    write_config "$local_dir"
    mkdir -p docs/decisions
    printf -- '---\nid: pending\nslug: first\ntitle: First\ndate: 2026-01-01\n---\n\nBody.\n' > docs/decisions/first.md
    git add -A
    git commit -q -m "add a pending record"
    git push -q origin main
  )
  echo "$local_dir"
}

feature_branch() {
  local local_dir="$1"
  (
    cd "$local_dir" || exit 1
    git switch -q -c feature
  )
}

run_check() {
  local local_dir="$1"
  # Check mode gets only what it needs: no REF, no DEFAULT_BRANCH, no gate, no bot.
  MODE=check CONFIG="$local_dir/stamp.json" STAMP_JS="$STAMP_JS" \
    bash -c "cd '$local_dir' && bash '$RUN_SH'" >"$WORK/check.log" 2>&1
}

test_check_mode_passes_pending_on_feature_branch() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  feature_branch "$local_dir"
  printf -- '---\nid: pending\nslug: second\ntitle: Second\ndate: 2026-01-02\n---\n\nBody.\n' > "$local_dir/docs/decisions/second.md"
  git -C "$local_dir" add -A
  git -C "$local_dir" commit -q -m "a pending record on a branch"
  local before_head remote_before
  before_head="$(git -C "$local_dir" rev-parse HEAD)"
  remote_before="$(git -C "$remote" rev-parse main)"

  GITHUB_ACTIONS=true run_check "$local_dir" || { echo "  expected exit 0"; cat "$WORK/check.log"; return 1; }
  [ "$(git -C "$local_dir" rev-parse HEAD)" = "$before_head" ] || { echo "  check mode made a commit"; return 1; }
  [ "$(git -C "$remote" rev-parse main)" = "$remote_before" ] || { echo "  check mode pushed"; return 1; }
  git -C "$local_dir" diff --quiet || { echo "  check mode wrote the tree"; return 1; }
  grep -q "id: pending" "$local_dir/docs/decisions/second.md" || { echo "  check mode stamped"; return 1; }
  grep -q "UNKNOWN:" "$WORK/check.log" && { echo "  output should not contain UNKNOWN:"; cat "$WORK/check.log"; return 1; }
  return 0
}

test_check_mode_refuses_number_on_feature_branch() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  feature_branch "$local_dir"
  printf -- '---\nid: D-002\nslug: second\ntitle: Second\ndate: 2026-01-02\n---\n\nBody.\n' > "$local_dir/docs/decisions/second.md"
  git -C "$local_dir" add -A
  git -C "$local_dir" commit -q -m "a record numbered on a branch"

  if run_check "$local_dir"; then
    echo "  expected a refusal, got exit 0"
    return 1
  fi
  grep -q "D-002 on a branch" "$WORK/check.log" || { echo "  the refusal did not name the record"; cat "$WORK/check.log"; return 1; }
  return 0
}

test_check_mode_refuses_unreadable_base() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  feature_branch "$local_dir"
  git -C "$local_dir" update-ref -d refs/remotes/origin/main

  if GITHUB_ACTIONS=true run_check "$local_dir"; then
    echo "  expected a refusal when origin/main is gone, got exit 0"
    return 1
  fi
  grep -q "could not run" "$WORK/check.log" || { echo "  the refusal did not say the read could not run"; cat "$WORK/check.log"; return 1; }
  return 0
}

# The same unreadable default base, but the base input names a ref git can read. The check runs
# against it: a record numbered on the branch is refused. So the input reached --base.
test_check_mode_base_input_passes_through() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  git -C "$local_dir" branch base-here
  feature_branch "$local_dir"
  git -C "$local_dir" update-ref -d refs/remotes/origin/main
  printf -- '---\nid: D-002\nslug: second\ntitle: Second\ndate: 2026-01-02\n---\n\nBody.\n' > "$local_dir/docs/decisions/second.md"
  git -C "$local_dir" add -A
  git -C "$local_dir" commit -q -m "a record numbered on a branch"

  if GITHUB_ACTIONS=true BASE=base-here run_check "$local_dir"; then
    echo "  expected a refusal against the base input, got exit 0"
    return 1
  fi
  grep -q "D-002 on a branch, and base-here" "$WORK/check.log" || { echo "  the check did not read the base input"; cat "$WORK/check.log"; return 1; }
  grep -q "could not run" "$WORK/check.log" && { echo "  the base input did not reach --base"; cat "$WORK/check.log"; return 1; }
  return 0
}

test_check_mode_refuses_pending_on_default_branch() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  if GITHUB_ACTIONS=true run_check "$local_dir"; then
    echo "  expected a refusal of a pending record on the default branch, got exit 0"; cat "$WORK/check.log"; return 1
  fi
  grep -q "id: pending" "$local_dir/docs/decisions/first.md" || { echo "  check mode wrote the tree"; return 1; }
  return 0
}

test_refuses_unknown_mode() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  if MODE=bogus CONFIG="$local_dir/stamp.json" STAMP_JS="$STAMP_JS" \
     bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected a refusal of an unknown mode, got exit 0"
    return 1
  fi
  return 0
}

run_test "check mode passes a pending record on a feature branch, and writes nothing" test_check_mode_passes_pending_on_feature_branch
run_test "check mode refuses a record numbered on a feature branch" test_check_mode_refuses_number_on_feature_branch
run_test "check mode refuses to pass when the base cannot be read" test_check_mode_refuses_unreadable_base
run_test "check mode passes the base input through to --base" test_check_mode_base_input_passes_through
run_test "check mode refuses a pending record on the default branch" test_check_mode_refuses_pending_on_default_branch
run_test "an unknown mode is refused" test_refuses_unknown_mode

echo "$((total - failed)) of $total passed."
[ "$failed" -eq 0 ]
