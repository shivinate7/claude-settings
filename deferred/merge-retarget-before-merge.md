# A base change just before the merge command is not caught

**What waits.** The merge tool reads the pull request base under the lock, and again on each
pass of the wait (plan ruling 12, plans/shared-merge-tool.md). If the base changes after the
last pass and before `gh pr merge`, the merge lands on the new base. The claim and the checks
were made for the old base.

**Why it waits.** It cannot be closed, only made smaller. `gh pr merge` and the GitHub merge API
pin the head (`--match-head-commit`), but not the base. A read of the base just before the merge
still leaves a window between that read and the merge. Today the window is a few seconds, and a
retarget during a merge has never been seen.

**The design, so the work is not lost.** One `host.pr(n)` read directly before `host.merge`. If
the base differs from the base read under the lock, stop, and revert a pushed claim through the
existing `fail()` path. Add a BaseAware case that changes the base after the wait.

**Trigger that brings it back.** A measured merge onto a base that changed during the run, or
GitHub adds a base pin to the merge API.

**Owner.** The claude-settings orchestrator that takes the next merge-tool change.
