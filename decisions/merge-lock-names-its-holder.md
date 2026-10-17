# The merge lock is a ref on origin, and it names its holder

## The ruling

1. The lock is a ref on origin, `refs/merge-lock/<base>`, made through the GitHub API. The API
   refuses a ref that exists, so only one session holds it. Cloud sessions merge too, and a
   file lock cannot see them.
2. The lock carries an expiry. A later run breaks an expired lock. `merge --unlock` removes
   a lock at once and reads no lock state first.
3. The lock commit records the PR, branch, host, platform, pid and start time. It records the
   session name from the optional `--session NAME` flag too.
4. The "held" message prints those fields and the time left. It says alive or dead only when
   the host and the platform match. Another host or platform, an old lock, or a garbled
   field reads "cannot tell".
5. `--unlock` stays unconditional. Nothing breaks a live lock by itself.
6. A release that fails, or finds another run's lock, says so in one line. It never raises.

Reason: an anonymous lock let an `--unlock` break a live merge, so a second PR merged in the gap.

Kind: build
Plan: decisions/merge-lock-names-its-holder.md#the-ruling (all)
Home: merge/merge.py

## Holes, named

- The expired-lock delete can remove a live lock (two runs can hold the lock).

## Related

- merge-follows-the-prs-base (the lock is per base, and `--unlock` takes a branch).
- merge-net-retry (a lock call that hits a rate limit or a network error).
