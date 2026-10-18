# A finished agent's shells keep its tree

**What.** A finished agent's own shells, such as a dev server, have the live host as parent.
No hook stops them, so they keep the worktree until the host exits. The owner ruled to stop
them (2026-10-15 19:43 CDT). That half is not built.

**Where.** `janitor/agent_end_reap.py`, the reaper's process test (read 3 keeps a process with
a live parent).

**Decision.** when-a-worktree-may-be-removed (when a worktree may be removed).

**Retire.** At a later agent end, the reaper stops the shells of a finished agent's tree
that is idle 30 min or more, then removes the tree. A test_sweep.py case shows a tree with a
host-child shell removed.
