#!/usr/bin/env bash
# Runnable self-test for run.sh (the composite action's own logic), against a real throwaway
# git remote. `bash actions/stamp/test_action.sh`. No framework: each test is a function: it
# prints "ok - <name>" and returns 0, or prints "FAIL - <name>" with the reason and returns 1.
set -uo pipefail

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

test_refuses_off_default_branch() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  local before_head
  before_head="$(git -C "$local_dir" rev-parse HEAD)"

  if REF="refs/heads/feature" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     GATE_COMMAND="true" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
     STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected a refusal, got exit 0"
    return 1
  fi
  [ "$(git -C "$local_dir" rev-parse HEAD)" = "$before_head" ] || { echo "  it touched HEAD"; return 1; }
  return 0
}

test_failed_gate_blocks_commit() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  local before_head
  before_head="$(git -C "$local_dir" rev-parse HEAD)"

  if REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     GATE_COMMAND="false" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
     STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected the gate failure to block the run, got exit 0"
    return 1
  fi
  [ "$(git -C "$local_dir" rev-parse HEAD)" = "$before_head" ] || { echo "  a commit landed despite the failed gate"; return 1; }
  [ "$(git -C "$remote" rev-parse main)" = "$before_head" ] || { echo "  the remote moved despite the failed gate"; return 1; }
  return 0
}

test_regenerate_runs_before_gate_in_same_commit() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"

  # The gate checks for a file only the regenerate command writes, so a gate that passes is
  # proof the regenerate command already ran, on the stamped tree, before the gate looked.
  if ! REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     REGENERATE_COMMAND="echo generated > generated.txt" \
     GATE_COMMAND="test -f generated.txt" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot \
     BOT_EMAIL=bot@example.com STAMP_JS="$STAMP_JS" \
     bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected success"
    return 1
  fi
  git -C "$remote" show main:generated.txt >/dev/null 2>&1 || { echo "  generated.txt did not reach the pushed commit"; return 1; }
  return 0
}

test_failed_regenerate_blocks_commit() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  local before_head
  before_head="$(git -C "$local_dir" rev-parse HEAD)"

  if REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     REGENERATE_COMMAND="false" GATE_COMMAND="true" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot \
     BOT_EMAIL=bot@example.com STAMP_JS="$STAMP_JS" \
     bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected the regenerate failure to block the run, got exit 0"
    return 1
  fi
  [ "$(git -C "$local_dir" rev-parse HEAD)" = "$before_head" ] || { echo "  a commit landed despite the failed regenerate command"; return 1; }
  [ "$(git -C "$remote" rev-parse main)" = "$before_head" ] || { echo "  the remote moved despite the failed regenerate command"; return 1; }
  return 0
}

test_succeeds_and_pushes() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"

  if ! REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     GATE_COMMAND="true" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
     STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected success"
    return 1
  fi
  local subject
  subject="$(git -C "$remote" log -1 --format=%s main)"
  [ "$subject" = "Stamp D-001" ] || { echo "  remote's subject was '$subject'"; return 1; }
  grep -q "id: D-001" "$local_dir/docs/decisions/first.md" || { echo "  the file was not stamped"; return 1; }
  return 0
}

test_gives_up_after_max_attempts() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  # A pre-receive hook that rejects every push, installed AFTER the setup push above, so the
  # retry loop can never catch up — the deterministic way to exercise "gives up after N
  # attempts" without racing a background push.
  cat > "$remote/hooks/pre-receive" <<'HOOK'
#!/usr/bin/env bash
echo "rejected by test fixture" >&2
exit 1
HOOK
  chmod +x "$remote/hooks/pre-receive"
  local before_head
  before_head="$(git -C "$local_dir" rev-parse HEAD)"

  if MAX_ATTEMPTS=2 REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     GATE_COMMAND="true" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
     STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir' && bash '$RUN_SH'" >"$WORK/out.log" 2>&1; then
    :
  else
    if [ "$(git -C "$remote" rev-parse main)" != "$before_head" ]; then
      echo "  the rejecting remote moved anyway"; return 1
    fi
    grep -q "attempt 2 of 2" "$WORK/out.log" || { echo "  did not retry up to the configured max"; cat "$WORK/out.log"; return 1; }
    grep -q "gave up after 2 attempts" "$WORK/out.log" || { echo "  did not report giving up"; return 1; }
    return 0
  fi
  echo "  expected the run to give up and fail"
  return 1
}

# clone_with_pending_record's local clone (the initial "add a pending record" push) needs a
# remote that accepts pushes even in the exhaustion test's setup phase, so the rejecting hook is
# installed AFTER that clone/push, not before. See test_gives_up_after_max_attempts.

run_test "refuses off the default branch" test_refuses_off_default_branch
run_test "a failed gate blocks the commit" test_failed_gate_blocks_commit
run_test "regenerate runs before the gate, in the same commit" test_regenerate_runs_before_gate_in_same_commit
run_test "a failed regenerate command blocks the commit" test_failed_regenerate_blocks_commit
run_test "stamps, gates, commits and pushes" test_succeeds_and_pushes
run_test "a push rejected every time gives up after the configured attempts" test_gives_up_after_max_attempts

echo "$((total - failed)) of $total passed."
[ "$failed" -eq 0 ]
