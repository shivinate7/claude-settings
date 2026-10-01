#!/usr/bin/env bash
# Runnable self-test for run.sh (the composite action's own logic), against a real throwaway
# git remote. `bash actions/stamp/test_action.sh`. No framework: each test is a function: it
# prints "ok - <name>" and returns 0, or prints "FAIL - <name>" with the reason and returns 1.
set -uo pipefail

# A CI run's own refs name the runner's branch, not a fixture's. GITHUB_ACTIONS picks a hard
# refusal or an UNKNOWN line for an unreadable base, so each test that reads one sets it itself.
unset GITHUB_REF GITHUB_BASE_REF GITHUB_ACTIONS MODE BASE
# Mode "stamp" needs a token. Every stamp test gets this one unless it sets its own.
TOKEN="tok-SECRET-0123"
export STAMP_TOKEN="$TOKEN"

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

test_regenerate_read_from_config_when_input_empty() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  node -e 'const f=process.argv[1],c=JSON.parse(require("fs").readFileSync(f,"utf8"));c.regenerate="echo generated > generated.txt";require("fs").writeFileSync(f,JSON.stringify(c))' "$local_dir/stamp.json"
  if ! REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     GATE_COMMAND="test -f generated.txt" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot \
     BOT_EMAIL=bot@example.com STAMP_JS="$STAMP_JS" \
     bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected success: the config's regenerate should have run before the gate"
    return 1
  fi
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

test_retry_reconciles_after_a_real_push_race() {
  local remote local_dir_a
  remote="$(new_bare_remote)"
  local_dir_a="$(clone_with_pending_record "$remote")"

  # While clone A's run is in flight, a second, unrelated clone merges its own new pending
  # record "second" straight to the remote — a merged PR, not a stamp run, so it lands
  # unstamped. Clone A never fetched it: A's tree still shows only "first" pending.
  local local_dir_b="$WORK/local-$RANDOM"
  git clone -q "$remote" "$local_dir_b" >/dev/null 2>/dev/null
  (
    cd "$local_dir_b" || exit 1
    git config user.email test@example.com
    git config user.name test
    printf -- '---\nid: pending\nslug: second\ntitle: Second\ndate: 2026-01-02\n---\n\nBody.\n' > docs/decisions/second.md
    git add -A
    git commit -q -m "add a pending record"
    git push -q origin main
  )

  # Clone A's stamp run derives D-001 for "first" against its now-stale tree, commits, and its
  # push collides with the real, moved remote — a genuine non-fast-forward rejection, not a
  # mocked hook. run.sh must then fetch, reset, and re-derive against the tree as it now
  # stands — which has grown a second pending record it never knew about — and retry (see
  # run.sh's "RE-DERIVE, NEVER REBASE" comment, and README.md's concurrency rule: "Two runs at
  # the same time could otherwise claim the same number").
  local out="$WORK/race-a.log"
  if ! REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir_a/stamp.json" \
     GATE_COMMAND="true" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
     STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir_a' && bash '$RUN_SH'" >"$out" 2>&1; then
    echo "  clone A's run was expected to survive the race and succeed"; cat "$out"; return 1
  fi
  grep -q "push rejected" "$out" || { echo "  clone A never hit a real push rejection; the race was not exercised"; cat "$out"; return 1; }
  grep -q "attempt 2" "$out" || { echo "  clone A never retried"; cat "$out"; return 1; }

  # Final origin state: both records numbered by the retry, unique, no gap, one stamp commit —
  # the re-derive picked up "second" and gave it a real number instead of dropping it, and gave
  # "first" whatever its fresh, reconciled position turned out to be, instead of replaying the
  # stale D-001 it computed before it knew "second" existed.
  local first_id second_id
  first_id="$(git -C "$remote" show main:docs/decisions/first.md | sed -n 's/^id: //p')"
  second_id="$(git -C "$remote" show main:docs/decisions/second.md | sed -n 's/^id: //p')"
  [ -n "$first_id" ] || { echo "  first.md was never numbered"; return 1; }
  [ -n "$second_id" ] || { echo "  second.md was never numbered"; return 1; }
  [ "$first_id" != "$second_id" ] || { echo "  first and second share an id: '$first_id'"; return 1; }
  local n1 n2 lo hi
  n1="${first_id#D-}"; n2="${second_id#D-}"
  n1=$((10#$n1)); n2=$((10#$n2))
  if [ "$n1" -lt "$n2" ]; then lo=$n1; hi=$n2; else lo=$n2; hi=$n1; fi
  [ "$lo" -eq 1 ] || { echo "  numbering does not start at 1: got $first_id and $second_id"; return 1; }
  [ "$hi" -eq 2 ] || { echo "  a gap between the two ids: got $first_id and $second_id"; return 1; }

  local stamp_commits
  stamp_commits="$(git -C "$remote" log --format=%s main | grep -c '^Stamp ')"
  [ "$stamp_commits" -eq 1 ] || { echo "  expected exactly one stamp commit from clone A's run, found $stamp_commits"; return 1; }
  return 0
}

test_refuses_empty_gate() {
  local remote local_dir
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  local before_head
  before_head="$(git -C "$local_dir" rev-parse HEAD)"

  if REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
     GATE_COMMAND="" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
     STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir' && bash '$RUN_SH'" >/dev/null 2>&1; then
    echo "  expected a refusal of an empty gate, got exit 0"
    return 1
  fi
  [ "$(git -C "$remote" rev-parse main)" = "$before_head" ] || { echo "  the remote moved with no gate"; return 1; }
  grep -q "id: pending" "$local_dir/docs/decisions/first.md" || { echo "  the tree was stamped with no gate"; return 1; }
  return 0
}

# Run run.sh in stamp mode against a fixture. Extra env goes in as arguments: "NAME=value".
stamp_run() {
  local local_dir="$1" gate="$2"
  shift 2
  env "$@" REF="refs/heads/main" DEFAULT_BRANCH="main" CONFIG="$local_dir/stamp.json" \
    GATE_COMMAND="$gate" SUBJECT_TEMPLATE="Stamp {ids}" BOT_NAME=bot BOT_EMAIL=bot@example.com \
    STAMP_JS="$STAMP_JS" bash -c "cd '$local_dir' && bash '$RUN_SH'" >"$WORK/stamp-run.log" 2>&1
}

# The gate (and the regenerate command) are the caller's code. They must see the token neither in
# their env nor in `git config --list`, and it must not be on the run's own output.
test_caller_code_never_sees_the_token() {
  local remote local_dir seen="$WORK/seen-$RANDOM"
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  local probe="{ env; git config --list; } > '$seen'"
  if ! stamp_run "$local_dir" "$probe" REGENERATE_COMMAND="{ env; git config --list; } > '$seen.regen'"; then
    echo "  expected success"; cat "$WORK/stamp-run.log"; return 1
  fi
  [ -s "$seen" ] || { echo "  the gate did not run"; return 1; }
  local b64
  b64="$(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')"
  local f
  for f in "$seen" "$seen.regen" "$WORK/stamp-run.log" "$local_dir/.git/config"; do
    grep -q -e "$TOKEN" -e "$b64" "$f" && { echo "  the token is visible in $f"; return 1; }
    grep -qi 'STAMP_TOKEN\|extraheader' "$f" && { echo "  a token variable or header is visible in $f"; return 1; }
  done
  return 0
}

# The fixture remote is a file path, so no HTTP header is ever read. A `git` wrapper on PATH
# records the argv and the per-command config env of each fetch and push, then runs real git.
# The push succeeds AND the wrapper saw the header for that exact token on the push, off argv.
test_push_carries_the_token_off_argv() {
  local remote local_dir bin="$WORK/bin-$RANDOM" log="$WORK/wrap-$RANDOM.log"
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  mkdir -p "$bin"
  local real_git
  real_git="$(command -v git)"
  cat > "$bin/git" <<WRAP
#!/usr/bin/env bash
case "\$1" in
  push|fetch) echo "\$1 argv=[\$*] key=[\${GIT_CONFIG_KEY_0:-}] value=[\${GIT_CONFIG_VALUE_0:-}]" >> "$log" ;;
esac
exec "$real_git" "\$@"
WRAP
  chmod +x "$bin/git"
  if ! stamp_run "$local_dir" "true" PATH="$bin:$PATH"; then
    echo "  expected success"; cat "$WORK/stamp-run.log"; return 1
  fi
  [ "$(git -C "$remote" log -1 --format=%s main)" = "Stamp D-001" ] || { echo "  the push did not land"; return 1; }
  local b64
  b64="$(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')"
  grep -q "^push .*key=\[http\.https://github\.com/\.extraheader\] value=\[AUTHORIZATION: basic $b64\]" "$log" \
    || { echo "  the push did not get the token header"; cat "$log"; return 1; }
  grep -q "$TOKEN" "$log" && { echo "  the raw token was seen by git"; return 1; }
  grep -q "$b64.*argv\|argv=\[[^]]*$b64" "$log" && { echo "  the token is on argv"; return 1; }
  return 0
}

test_stamp_refuses_empty_token() {
  local remote local_dir before_head
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  before_head="$(git -C "$remote" rev-parse main)"
  if stamp_run "$local_dir" "true" STAMP_TOKEN=""; then
    echo "  expected a refusal of an empty token, got exit 0"; return 1
  fi
  grep -q "needs a token" "$WORK/stamp-run.log" || { echo "  the refusal did not name the token"; cat "$WORK/stamp-run.log"; return 1; }
  [ "$(git -C "$remote" rev-parse main)" = "$before_head" ] || { echo "  the remote moved with no token"; return 1; }
  grep -q "id: pending" "$local_dir/docs/decisions/first.md" || { echo "  the tree was stamped with no token"; return 1; }
  return 0
}

test_stamp_refuses_persisted_credential() {
  local remote local_dir before_head
  remote="$(new_bare_remote)"
  local_dir="$(clone_with_pending_record "$remote")"
  before_head="$(git -C "$remote" rev-parse main)"
  git -C "$local_dir" config http.https://github.com/.extraheader "AUTHORIZATION: basic cGVyc2lzdGVk"
  if stamp_run "$local_dir" "true"; then
    echo "  expected a refusal of a persisted extraheader, got exit 0"; return 1
  fi
  grep -q "persist-credentials: false" "$WORK/stamp-run.log" || { echo "  the refusal did not name the remedy"; cat "$WORK/stamp-run.log"; return 1; }
  [ "$(git -C "$remote" rev-parse main)" = "$before_head" ] || { echo "  the remote moved despite the persisted credential"; return 1; }
  grep -q "id: pending" "$local_dir/docs/decisions/first.md" || { echo "  the tree was stamped despite the persisted credential"; return 1; }
  return 0
}

# A feature branch off the fixture's main, pushed, so origin/main is the base check mode reads.
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

# clone_with_pending_record's local clone (the initial "add a pending record" push) needs a
# remote that accepts pushes even in the exhaustion test's setup phase, so the rejecting hook is
# installed AFTER that clone/push, not before. See test_gives_up_after_max_attempts.

run_test "refuses off the default branch" test_refuses_off_default_branch
run_test "a failed gate blocks the commit" test_failed_gate_blocks_commit
run_test "regenerate runs before the gate, in the same commit" test_regenerate_runs_before_gate_in_same_commit
run_test "regenerate is read from the config when the input is empty" test_regenerate_read_from_config_when_input_empty
run_test "a failed regenerate command blocks the commit" test_failed_regenerate_blocks_commit
run_test "stamps, gates, commits and pushes" test_succeeds_and_pushes
run_test "a push rejected every time gives up after the configured attempts" test_gives_up_after_max_attempts
run_test "a real push race is resolved by retry: no duplicate, no gap" test_retry_reconciles_after_a_real_push_race
run_test "stamp mode refuses an empty gate command" test_refuses_empty_gate
run_test "caller code (gate, regenerate) never sees the token" test_caller_code_never_sees_the_token
run_test "the push carries the token, off argv" test_push_carries_the_token_off_argv
run_test "stamp mode refuses an empty token" test_stamp_refuses_empty_token
run_test "stamp mode refuses a credential persisted in .git/config" test_stamp_refuses_persisted_credential
run_test "check mode passes a pending record on a feature branch, and writes nothing" test_check_mode_passes_pending_on_feature_branch
run_test "check mode refuses a record numbered on a feature branch" test_check_mode_refuses_number_on_feature_branch
run_test "check mode refuses to pass when the base cannot be read" test_check_mode_refuses_unreadable_base
run_test "check mode passes the base input through to --base" test_check_mode_base_input_passes_through
run_test "an unknown mode is refused" test_refuses_unknown_mode

echo "$((total - failed)) of $total passed."
[ "$failed" -eq 0 ]
