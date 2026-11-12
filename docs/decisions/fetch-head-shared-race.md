# A read of FETCH_HEAD must follow its own fetch in the same command

## The ruling

A Bash command that reads `FETCH_HEAD` is refused unless an earlier segment of the same command runs `git fetch` (rule `fetch-head-read`). The remedy is `git fetch origin <b>:refs/remotes/origin/<b>`, then a read of `origin/<b>`. The refusal never names the file it refuses.

- The guard reads parsed tokens of a segment whose command word is `git`. A read is a ref argument of `show`, `log`, `diff`, `rev-parse`, `cat-file`, `merge` or another read verb that is `FETCH_HEAD`, or a range or revision form of it (`HEAD...FETCH_HEAD`, `FETCH_HEAD:path`, `FETCH_HEAD^{commit}`).
- An echo, a grep pattern, a commit message, quoted text and a read of `origin/<b>` pass. A fetch after the read, or named only in quotes, clears nothing. A fetch in the outer text clears a read in a `$( )` text of the same command.
- `GitLock.read` in `merge/merge.py` takes the lock commit's text by the sha `ls-remote` returned, never `FETCH_HEAD`. `relayed_head_holds` fetches into `refs/remotes/origin/<branch>` and reads that ref. A moved lock has no object for the old sha, so the read reports the lock as live, the safe side.
- Left as they are, each in a clone no other agent fetches in: `bin/ci-job` (its own temp clone), `install.sh` `mirror_refresh` (the mirror clone), `hooks/session_start.sh`, and `githooks/main-ref/reference-transaction`, which reads the file on purpose, inside git's own transaction.
- Known limits, not counted: `cat .git/FETCH_HEAD` is no git read and passes. No ruling covers it. `git pull` counts as no fetch. A fetch that fails before a `;` read still clears it. A fetch and a read in one command still share a window, but no other command runs between them.

Why: 2026-11-12 12:41 to 12:52 CST, two read-only audit agents shared one checkout (rule `parallelism-each-own-checkout`, read-only agents share the caller's checkout). Each fetched, then ran `git show FETCH_HEAD:...`. The other agent's fetch moved `FETCH_HEAD` between a fetch and a read, and PR 2745 got a wrong read. One transcript held 42 uses of the file. The outcome it protects: a read of a branch returns that branch, so a review or a merge check never judges another agent's ref. A read of a named remote-tracking ref changes only when its own fetch changes it.

Risk kind: incident, 2026-11-12 12:41 CST. The guard it asks for (rule `building-mistake-names-its-guard`, a mistake names the guard that would have stopped it): built here, with the debt `fetch-head-read-gaps` for the gaps above.

Kind: process
Home: hooks/guard_merge.py
