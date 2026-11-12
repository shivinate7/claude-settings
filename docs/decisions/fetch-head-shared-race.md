# A read of FETCH_HEAD must follow its own fetch in the same command

## The ruling

A Bash command that reads `FETCH_HEAD` is refused unless an earlier segment of the same command runs `git fetch` (rule `fetch-head-read`). The remedy is `git fetch origin <b>:refs/remotes/origin/<b>`, then a read of `origin/<b>`. The refusal never names the file it refuses.

- The guard reads parsed tokens of a segment whose command word is `git`. A read is a ref argument of `show`, `log`, `diff`, `rev-parse`, `cat-file`, `merge` or another read verb that is `FETCH_HEAD`. A verb that takes a ref as a start point or target reads it too (`worktree add <dir>`, `branch <b>`, `tag`, `push`, `restore`, `grep <pattern>`, `archive`, `revert`, `update-ref`, `read-tree`, `range-diff`). So does a range or revision form of it (`HEAD...FETCH_HEAD`, `FETCH_HEAD..HEAD`, `FETCH_HEAD...HEAD`, `FETCH_HEAD:path`, `FETCH_HEAD^{commit}`). A path named `FETCH_HEAD.md` is no ref.
- `-m` and `-F` are booleans for `log` and `show`, so `git show -m FETCH_HEAD` reads; they take a value only in `merge`, `tag`, `cherry-pick` and `revert`. `--pretty` and `--format` take a value after `=` only. `--grep`, `-S`, `-G`, `--author`, `--committer`, `--since`, `--until` and `-e` take the next word as a value. `commit -m FETCH_HEAD` and `log --grep FETCH_HEAD` pass.
- `git rev-parse --git-path FETCH_HEAD` prints where the file lives and reads no content, so it passes.
- An echo, a grep pattern, a commit message, quoted text and a read of `origin/<b>` pass. A fetch after the read, or named only in quotes, clears nothing. The `$( )` texts of a segment run before the segment's own command, in text order, so `echo $(git show FETCH_HEAD:p); git fetch origin x` is refused: a later fetch clears nothing.
- `GitLock.read` in `merge/merge.py` takes the lock commit's text by the sha `ls-remote` returned, never `FETCH_HEAD`. `relayed_head_holds` fetches into `refs/remotes/origin/<branch>` and reads that ref. The fetch brings the lock ref's tip. When the lock moved after the `ls-remote`, the old sha has no object here and `git log` fails, so the read reports the lock as live: a take-over is refused and the next read sees the new sha, never a wrong take-over.
- Left as they are, each in a clone no other agent fetches in: `bin/ci-job` (its own temp clone), `install.sh` `mirror_refresh` (the mirror clone; it reads `FETCH_HEAD` only after fetching the same `$REF`, so it is benign), `hooks/session_start.sh`, and `githooks/main-ref/reference-transaction`, which reads the file on purpose, inside git's own transaction.
- Skills, agents and brief templates hold no `FETCH_HEAD` read, so the remedy needs no edit there.
- Known limits, listed in debt `fetch-head-read-gaps`: `cat .git/FETCH_HEAD` is no git read and passes. No ruling covers it. `git pull` counts as no fetch: a `git pull` then a read is refused, an over-refusal, not a miss. A fetch that fails before a `;` or `|` read still clears it, because the check reads text and never an exit code. `git -C <other> fetch` then a bare read passes, since the fetch is of another checkout. A fetch and a read in one command still share a window: another agent can fetch inside it, so the check narrows the race and does not close it. A read named `--source=FETCH_HEAD` or `--onto=FETCH_HEAD` is no word the check reads.

Why: 2026-11-12 12:41 to 12:52 CST, two read-only audit agents shared one checkout (rule `parallelism-each-own-checkout`, read-only agents share the caller's checkout). Each fetched, then ran `git show FETCH_HEAD:...`. The other agent's fetch moved `FETCH_HEAD` between a fetch and a read, and PR 2745 got a wrong read. One transcript held 42 uses of the file. The outcome it protects: a read of a branch returns that branch, so a review or a merge check never judges another agent's ref. A read of a named remote-tracking ref changes only when its own fetch changes it.

Risk kind: incident, 2026-11-12 12:41 CST. The guard it asks for (rule `building-mistake-names-its-guard`, a mistake names the guard that would have stopped it): built here, with the debt `fetch-head-read-gaps` for the gaps above.

Kind: process
Home: hooks/guard_merge.py
