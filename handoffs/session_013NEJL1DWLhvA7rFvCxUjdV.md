# brief-destructive-git-windows (main red fix) (session_013NEJL1DWLhvA7rFvCxUjdV), received 09:52 CST 2026-11-10, kind B

Handoff (B), lane brief-destructive-git-windows, session_013NEJL1DWLhvA7rFvCxUjdV:
1. Work: fix main red (two Windows-only brief-destructive-git cases). Cause: posix shlex drops the backslashes of a brief's `git -C C:\...\scratchpad\repo`. Then told to stop: #2390 fixes it test-side.
2. shivinate7/claude-settings: draft PRs #2407 (head 8edc310fc) and #2408 (head ce13f7405), both marked replaced by #2390, no review record on either. Archive branches pushed: archive/brief-destructive-git-win, archive/brief-destructive-git-win-red, archive/brief-destructive-git-fix.
3. State: nothing unpushed that matters; a local-only branch in the builder worktree duplicates the fix branch. Nothing running.
4. Left: triage closes #2407 and #2408 and the three original origin branches.
