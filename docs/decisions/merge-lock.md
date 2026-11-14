# The merge lock

## The ruling

One lock holds each base branch while a merge run works on it. The run takes the lock before it claims
record numbers, waits on checks or merges. It releases the lock when it ends. Two runs cannot hold the
lock for one base at once. Code: `confirm` in `merge/merge.py`.

- **Holder.** The lock is the ref `refs/heads/merge-lock/<base>`. Its commit message holds `expires`, an
  `owner` id, and the holder: `pr`, `branch`, `host`, `platform`, `pid`, `started`, `boot` (only when
  readable) and `session` (80 characters at most). `confirm` sets the holder before the take. Code:
  `lock_message`.
- **Time limit.** The take sets the expiry to 20 minutes after the take (`LOCK_TTL_SECONDS`, 1200 s),
  at every `merge.deadlineMinutes`. The value is unmeasured. A lock past its expiry is free. Another
  run may take it. `LOCK_MAX_HOLD` (6 h from the take) bounds the extensions only.
- **Extend.** Before each rate-limit wait, and before the lint run and the suite run of the small-move
  check, `Lock.extend_for` moves the expiry to now + wait + 300 s. The wait is the rate wait, or 3600 s
  for a lint or suite run. It does nothing when the expiry already covers that time. It stops (`NetStop`) when
  the lock has expired, when the new expiry passes 6 h from the take, or when the push fails.
- **Take over.** A live lock stops the run (`Held`). The exception is a holder whose pid is gone on the
  same host, platform and boot. Then one line says the take goes on. A holder that cannot be checked reads
  as unknown. Its lock stops the run, and the message says to ask the owner before `merge --unlock`. A live
  lock under the old name `refs/merge-lock/<base>` always stops the run on `GitLock`. `GhLock` does not
  read the old name. Code: `holder_state`,
  `refuse_or_take_over`, `refuse_old_lock`.
- **Backends.** `GitLock` runs when `CLAUDE_CODE_REMOTE` is `true`. It takes and swaps the lock with leased
  pushes. `GhLock` runs otherwise. It takes and swaps the lock with the GitHub API. Code: `default_lock`.
- **Release.** The run's `finally` releases its lock. The release removes the ref only while the ref holds
  one of this run's commits. A release that fails prints one line. It stops nothing.
- **Unlock.** `merge --unlock [branch]` removes the lock for the branch, or for the default branch when no
  branch is named. It removes the lock whether its holder is live or not. It prints "removed", or "nothing
  to remove" when no lock is there.

Stops, by name. Each name is a row label of the refusal-vs-rule sweep, a plan record. The code
carries no such label. The code raises the exception named in each item.

- `Held` (sweep row `lock-held`): a live lock whose holder is not dead, a live lock under the old name
  (`GitLock` only), or a lost take race.
- Lock unreadable (sweep row `lock-acquire-unreadable`; `Stop`, or `NetStop` on a network error): the ref,
  the lock commit or the base branch cannot be read, or the lock commit or the take cannot be made.
- Extend failed (sweep row `lock-extend-failed`; `NetStop`): the lock expired before the wait, the
  extension would pass 6 h, or the push failed.
- Rate wait unextendable (sweep row `rate-wait-unextendable`; `NetStop`): a GitHub rate-limit wait needs
  the lock extended first, and the extension fails. Code: `retry_net`.
- Unlock failed (sweep row `unlock-failed`; `NetStop` or `Stop`): the delete fails. On `GitLock` the
  released-commit push fails too.

Why: a claim, a check wait and a merge must not race another run on the same base. The claim runs under
the lock (`records-index-at-merge`, the records index rebuilt at merge time).

Known gaps, all in `docs/debts/notes.md`:

- `merge-lock-expired-delete-race`: `GhLock` deletes an expired lock with no compare-and-swap, so a live
  lock taken in the gap can be removed.
- `ghlock-no-compare-and-swap`: the API ref update has no compare-and-swap, so an expiring lock can be
  overwritten between the read and the write.
- `expired-delete-net-error-stops`: the delete of an expired lock runs once, so a network error stops the run.
- `lock-read-error-never-expires`: `GhLock.read` gives an infinite expiry when the lock commit cannot be
  read for a reason other than the network, so that lock never expires.

Risk: likely risk (`building-guard-needs-incident`: a guard or check needs a mistake Claude has made or is
likely to make in normal work). Two runs on one base would race, and batches often run while another batch merges
(`merge-needs-current-base`). Landed 2026-09-30, the first merge lock in `merge/merge.py`.

Kind: process
Home: merge/merge.py
