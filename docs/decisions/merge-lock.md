# The merge lock

## The ruling

One lock holds each base branch while a merge run works on it. The run takes the lock before it claims
record numbers, waits on checks or merges. It releases the lock when it ends. Two runs cannot hold the
lock for one base at once, with two exceptions until each old-code run exits (decision
`merge-reinstalls-from-main`: each merge reinstalls from main). An old-code run still on the deleted API lock
can delete a new take. A run older than c53 takes the old name `refs/merge-lock/<base>` and never reads the
new name. So it can hold the old name while a new run holds the new one. Code: `confirm` in
`merge/merge.py`.

- **Holder.** The lock is the ref `refs/heads/merge-lock/<base>`. Its commit message holds `expires`, an
  `owner` id, and the holder: `pr`, `branch`, `host`, `platform`, `pid`, `started`, `boot` (only when
  readable) and `session` (80 characters at most). `confirm` sets the holder before the take. Code: `lock_message`.
- **Time limit.** The take sets the expiry to (3 x `merge.deadlineMinutes` + 10) minutes. The default
  deadline is 45 minutes, so the expiry is 8700 s after the take. A lock past its expiry is free. Another
  run may take it. `LOCK_MAX_HOLD` (6 h from the take) bounds the extensions only.
- **Extend.** Before each rate-limit wait, and before the lint run and the suite run of the small-move
  check, `Lock.extend_for` moves the expiry to now + wait + 300 s. The wait is the rate wait, or 1200 s
  for a lint or suite run. It does nothing when the expiry already covers that time. It stops (`NetStop`) when
  the lock has expired, when the new expiry passes 6 h from the take, or when the push fails.
- **Take over.** A live lock stops the run (`Held`). The exception is a holder whose pid is gone on the
  same host, platform and boot. Then one line says the take goes on. A holder that cannot be checked reads
  as unknown. Its lock stops the run, and the message says to ask the owner before `merge --unlock`. A live
  lock under the old name `refs/merge-lock/<base>` always stops the run. Code: `holder_state`,
  `refuse_or_take_over`, `refuse_old_lock`.
- **Backend.** `GitLock` on every host. Leased pushes take, swap and release the lock.
- **Release.** The run's `finally` releases its lock. The release removes the ref only while the ref holds
  one of this run's commits. It deletes the ref with a leased push. A cloud proxy refuses ref deletes (HTTP
  403). There the release pushes an expired commit under the same lease instead: the ref stays, and any run
  may take it. A release that fails prints one line. It stops nothing.
- **Unlock.** `merge --unlock [branch]` removes the lock for the branch, or for the default branch when no
  branch is named. It removes the lock whether its holder is live or not, and even when its commit cannot be
  read. The delete is a leased push on the sha it listed, so a lock taken after the listing stays. It prints
  "removed", or "nothing to remove" when no lock is there or the lock is already released (expires 0). A
  released lock whose commit cannot be read is released again, and it prints "removed".
  Where the delete is refused, it releases the lock to an expired commit instead, and it still prints
  "removed".

Stops, by name. Each name is a row label of the refusal-vs-rule sweep, a plan record. The code
carries no such label. The code raises the exception named in each item.

- `Held` (sweep row `lock-held`): a live lock whose holder is not dead, a live lock under the old name,
  or a lost take race.
- Lock unreadable (sweep row `lock-acquire-unreadable`; `Stop`, or `NetStop` on a network error): the ref
  cannot be read, the lock commit cannot be read over the network, or the lock commit or the take cannot be
  made. A non-network fetch failure, or a failed `git log` of the listed sha, re-lists once, then `Stop`.
  The take push runs once, by design: a network error on it stops the run only when the take did not
  land. A take that landed with a lost reply proceeds.
- Extend failed (sweep row `lock-extend-failed`; `NetStop`): the lock expired before the wait, the
  extension would pass 6 h, or the push failed.
- Rate wait unextendable (sweep row `rate-wait-unextendable`; `NetStop`): a GitHub rate-limit wait needs
  the lock extended first, and the extension fails. Code: `retry_net`.
- Unlock failed (sweep row `unlock-failed`; `Stop`): the delete push fails, the released-commit push
  fails too, and the ref is still listed.

Known gaps, in `docs/debts/notes.md`:

- `lock-retake-stale-reread`: a stale `ls-remote` after a rival's take reads as `Stop`, not `Held`.
  Unmeasured.
- `lock-push-429-stops`: git's `returned error: 429` line stops a lock push or read, with no retry. Unmeasured.

Why: a claim, a check wait and a merge must not race another run on the same base. The claim runs under
the lock (`records-index-at-merge`, the records index rebuilt at merge time).

Risk: likely risk (`building-guard-needs-incident`: a guard or check needs a mistake Claude has made or is
likely to make in normal work). Two runs on one base would race, and batches often run while another batch merges
(`merge-needs-current-base`). Landed 2026-09-30, the first merge lock in `merge/merge.py`.

Kind: process
Home: merge/merge.py
