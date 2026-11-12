# A roadmap step waits on a step slug, never on a bare PR number

## The ruling

Owner, 2026-11-10 13:09 CST and 13:10 CST (chat): a roadmap step that waits on another piece of work names the step slug in its `blockedBy` list. It never waits on a bare PR number. A pull request can close unmerged, and then nobody acts on the wait.

- Guard rule `dead-pr-wait` (`dead_pr_wait_hit` in `hooks/guard_merge.py`, run by `hooks/guard.py`) refuses a Write, Edit or MultiEdit to `roadmap/data/steps/<name>.json` that adds a wait on `#N` or `PR #N` to the step's `title`, `why`, `note` or `ask`. It refuses only when the step has no slug in `blockedBy`. The wait words are `DEAD_PR_WAIT_PHRASES` in `hooks/shared_names.py`, the one matcher the build shares.
- The roadmap build (`skills/roadmap/build.py`) prints a `dead PR wait` line for each open step that still waits on a bare number. The line reads `closed and not merged` and the build exits 1 when the live file shows that PR closed unmerged.
- The remedy is the step's `blockedBy` slug, or dropping the wait.

Risk kind: likely risk. A session writes "waits on #N" in a step note in normal work. Known limits are filed as notes under step `dead-pr-waits` in `docs/debts/notes.md`.
