---
name: verify-hooks
description: Use when a lane changes a claude-settings hook that runs at session start, or any hook whose result lands in a state file, before you call it done. Not for ordinary code edits. Proves the real hook script on a fixture repo, in a fresh clone of the pushed branch.
---

A green fixture test proves only its platform and the states its fixtures build (rule
verification-green-proves-only-its-fixtures). A hook change is done when the real hook, started
the way the harness starts it, leaves the state it should. Push the branch, then run these steps
before you call the hook done.

## Procedure

1. **Name the state.** Say which file the hook writes and what it holds. For the standing merge
   role it is `<home>/.claude/state/merge-role.json`, `{"session": "cse_<x>", "role": "standing"}`.
2. **Start the real hook.** Use `hooks/session_start.sh`, never a stub or a copy. Give it a fresh
   temp HOME and no `CLAUDE_CONFIG_DIR`, so it reads `<home>/.claude` as a cloud container does.
   Set `CLAUDE_CODE_REMOTE=true` and `CLAUDE_CODE_REMOTE_SESSION_ID=cse_<x>`. Send the payload on
   stdin: `{"cwd": ..., "session_id": ...}`. The roster row comes from the `origin/roadmap` ref.
   `SessionStartRosterTests` in `hooks/test_session_start.py` builds all of this once, in its
   `start_fresh_cloud` method. Step 4 runs it. Do not rebuild it by hand.
3. **Know what the case reads.** The case opens the file from step 1 and checks its content, not
   only that it exists. A control row (a batch runner) must leave no file. The test deletes its
   temp HOME when it ends, so you cannot open the file after step 4. A check you want on the file
   goes in the case.
4. **Run the case in a fresh clone, through verdict.** A fresh clone holds only pushed files, so a
   file you forgot to commit or push shows up as a failure here.

       dir=$(mktemp -d) && git clone -q -b <branch> <repo-url> "$dir/c" && cd "$dir/c"
       ~/.claude/bin/verdict python3 hooks/test_session_start.py -k merge_role_file

   Run `verdict` with nothing after it. A pipe hides its result.
5. **Read the one-line verdict.**
   - With the hook: `PASS python3 hooks/test_session_start.py -k merge_role_file (<secs>s)`.
   - Without the hook (the step 6 commit): `FAIL python3 hooks/test_session_start.py -k merge_role_file rc=1 (<secs>s) log=<path>`.
     The log says `the cloud start wrote no merge role file`.
   A `SKIP` line means that a case did not run. Treat it as no proof.
6. **Show it red first.** Run step 4 on the commit that holds the case but not the hook change
   (the test-author's commit), and see the FAIL line. Main has no case to run. Clone, then check
   the commit out:

       git clone -q <repo-url> "$dir/r" && cd "$dir/r" && git checkout -q <sha>
       ~/.claude/bin/verdict python3 hooks/test_session_start.py -k merge_role_file

   A case that never went red proves nothing (rule verification-trust-guard-after-red).

## What a green does not prove

- A green proves only the states the fixtures build. The case runs the real script on a fixture
  repo, one roster row and a fixture `origin/roadmap` ref. It does not prove the roster of a live repo.
- It runs on one platform. A cloud container differs in its network, its user and its clock.
- The hook ran on a fresh HOME. A HOME with an old state file is a different start. Say which
  one you proved.
- A step you could not run reads as unknown. Report it as unknown, never as clear.

Report the verdict line of step 5 and the FAIL line of step 6.
