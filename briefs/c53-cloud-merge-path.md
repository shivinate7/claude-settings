# c53 part 2: a merge path the cloud proxy allows

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main 3b96ce8 (or the
newest main). Never rebase onto main after review. claude-settings only. Push roadmap edits to
the branch only; only Triage the roadmap (3) republishes.

## Finding

Oct 26, #617: from a full clone, `python3 merge/merge.py 617` previewed clean; `--confirm` stopped
at "cannot make the lock commit": gh got HTTP 403 "Write access to this GitHub API path is not
permitted through this proxy". Nothing was written. The Mac merge hand merges every batch until
this lands. shiv's ruling (c53, a): the next batch merges from the cloud, the Mac as fallback.

## Task

1. Measure first, on throwaway branches only (never main, never a real batch): which merge.py
   writes the cloud proxy allows. Try each write merge.py makes (lock commit, records commit push,
   PUT pulls/N/merge, branch deletes) against a throwaway base branch and a throwaway PR into it.
   Also try `git push` of a lock ref and the GitHub MCP merge tool (mcp__github__merge_pull_request)
   with the head sha guard. Record each as allowed or refused, with the exact error.
2. If a full path exists: give merge.py a cloud mode that uses only allowed writes (for example a
   lock ref by git push with lease; the merge by the MCP tool, which a Python script cannot call, so
   the script stops at "ready to merge <sha>" and the session calls the tool, then reruns merge.py
   to finish the after-merge steps). Keep one tool: extend merge.py, never a second script. The Mac
   path stays as it is.
3. If no full path exists: say so with the table; c53 stays Mac-only. Build nothing.
4. Delete every throwaway branch and close every throwaway PR you made.

## Failure classes and proof

- Test-author first, red on main: cloud mode never calls a refused API path (a mock refuses it);
  the lock is held while a second run waits; a moved head stops the merge; the after-merge rerun
  is a no-op when main already has the merge.
- merge/test_merge.py and every gates.yml step locally before sending.
- A fresh Sonnet reviewer reads the diff (it changes the merge gate).

## Report

Cap 20 lines: the allowed/refused table, Done, Deviations, Next, and "Port to other repos: yes or
no, and why". Send the green, reviewed head and branch to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft.
