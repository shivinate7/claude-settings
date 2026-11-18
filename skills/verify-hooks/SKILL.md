---
name: verify-hooks
description: Use when a lane changes a claude-settings hook that runs at session start, or any hook whose result lands in a state file, before you commit it or call it done. Not for ordinary code edits. Proves the hook on the real thing, not on fixtures alone.
---

A green fixture test proves only its platform and the states its fixtures build (rule
verification-green-proves-only-its-fixtures). A hook change is done when the real hook, started
the way the harness starts it, leaves the state it should. Run these steps before you commit.

## Procedure

1. **Name the state.** Say which file the hook writes and what it holds. For the standing merge
   role it is `<home>/.claude/state/merge-role.json`, `{"session": "cse_<x>", "role": "standing"}`.
2. **Start the real hook.** Use `hooks/session_start.sh`, never a stub or a copy. Give it a fresh
   temp HOME and no `CLAUDE_CONFIG_DIR`, so it reads `<home>/.claude` as a cloud container does.
   Set `CLAUDE_CODE_REMOTE=true` and `CLAUDE_CODE_REMOTE_SESSION_ID=cse_<x>`. Send the payload on
   stdin: `{"cwd": ..., "session_id": ...}`. The roster row comes from the `origin/roadmap` ref.
   `SessionStartRosterTests` in `hooks/test_session_start.py` builds all of this once. Start
   through its `start_fresh_cloud` helper. Do not rebuild it by hand.
3. **Read the state file.** Open the file from step 1 and check its content, not only that it
   exists. Check that a control row (a batch runner) leaves no file.
4. **Run the case in a fresh clone, through verdict.** A fresh clone holds only committed files, so
   a file you forgot to commit shows up as a failure here.

       dir=$(mktemp -d) && git clone -q -b <branch> <repo-url> "$dir/c" && cd "$dir/c"
       ~/.claude/bin/verdict python3 hooks/test_session_start.py -k merge_role_file

   Run `verdict` with nothing after it. A pipe hides its result.
5. **Read the one-line verdict.**
   - With the hook: `PASS python3 hooks/test_session_start.py -k merge_role_file (<secs>s)`.
   - Without the hook (main): `FAIL python3 hooks/test_session_start.py -k merge_role_file rc=1 (<secs>s) log=<path>`.
     The log says `the cloud start wrote no merge role file`.
   A `SKIP` line means a case did not run. Treat it as no proof.
6. **Show it red first.** Run step 4 on the base commit and see the FAIL line. A case that never
   went red proves nothing (rule verification-trust-guard-after-red).

## What a green does not prove

- A green on fixtures alone proves only the states those fixtures build. The case builds one
  roster row and a local `origin/roadmap` ref. It does not prove the roster of a live repo.
- It runs on one platform. A cloud container differs in its network, its user and its clock.
- The hook ran on a fresh HOME. A HOME with an old state file is a different start. Say which
  one you proved.
- A step you could not run reads as unknown. Report it as unknown, never as clear.

Report the verdict line of step 5 and the base commit's FAIL line.
