# A port held by another checkout is refused

## The question

Parallel lanes run in separate worktrees of one clone. How does a lane avoid testing another
lane's server by accident?

## The ruling

Owner, 2026-10-11 (rule `port-other-checkout` in `hooks/guard.py`):

1. When a Bash command names a port, the guard reads who listens on that port now. A port is
   named by an assignment called `PORT` or ending in `_PORT`, or by `--port n`.
2. When the listener runs from another checkout of the same clone, the guard refuses.
3. Every other case is allowed: the same checkout, no listener, a listener in another repo or
   in no repo, or a read that fails.
4. A live check, not a lease. A lease cannot make a server bind its port, and a lease that
   outlives its server refuses falsely.

## The incident

2026-10-11, feed-build: a builder and a test-author ran Playwright with `PW_PORT=5397` in
separate worktrees. Playwright reuses a server that already holds the port, so one lane could
pass or fail on the other lane's code. The orchestrator saw it in a progress note. No check
caught it.

## Named limits

- A port set only in a config file, in a package script, or by a default is not seen.
- Two lanes that start in the gap between the check and the bind both pass.
- `-p n`, `docker -p`, a `localhost:n` URL, and a server whose working folder is not its
  checkout are not covered.
- The root cause is Playwright's server reuse. Whether repos fix that is open; see decision
  worktree-setup-is-per-repo.
