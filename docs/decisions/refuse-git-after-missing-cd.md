# Refuse a git write after a cd into a missing folder

## The ruling

The guard refuses a git write after a `cd` only when the `cd` names a folder that is missing at check time. A `cd` into a folder that exists still passes, whether `;`, a newline or `||` follows it. `cd <missing> && <write>` still passes, because the failed `cd` stops the chain. The newline and `||` forms come from the build, not the ruling.

- Source: ruling own-476-c-refuse-cd-missing-folder, the owner's pick c on waiting-page item 476 ("Refuse only a cd into a missing folder (Recommended)"), 2026-11-16 13:36 CST, no note.
- Writes covered: any git write, such as add, commit, push, merge and `--continue`.
- The cost the owner named: a folder removed between the check and the run still slips.
- Open: waiting-page item 912 asks about the same case (option a: keep the refusal and re-point the test). The owner has not picked an option. The answer was "none of these", with notes. This ruling does not close it.
- The mistake: a `cd` into a missing folder leaves the shell in its old folder, so a write after `;` runs in the old repository.
- The harm: the write lands in the wrong repository.

## The build

The guard change in PR 3594 builds the ruling. Until it merges, main does not refuse this write.

- Rule `conflict-markers` refuses every git write in `GIT_WRITES`: add, commit, push, merge, pull, rebase, cherry-pick, `--continue`, reset and the rest. A git read, such as status, passes. The list counts `stash list`, `tag -l` and `config --get` as writes, so those are refused too.
- A folder that an earlier part of the same call makes counts as present: a `mkdir` (with its parent present, or with `-p`), a `git clone`, a `git init` or a `git worktree add`.
- A failed `cd` then `|| exit` ends the shell, so nothing after it runs and the call passes. A failed `cd` then `|| return` does not: outside a function, bash reports an error and the next command runs, so the write is refused.
- A forced push after such a `cd` gets force-push's own ask first. When chained, rule `ask-alone` denies it.
- The refusal also needs the folder the shell stays in to be a git checkout (`_repo_of` in `hooks/guard_merge.py`). So a `git clone` or `git init` from a folder that is not a checkout is not refused.
- The build covers less than the ruling. Verbs outside `GIT_WRITES` are not refused, such as `branch`, `worktree`, `fetch`, `notes`, `submodule`, `remote`, `update-ref` and `gc`.
- False alarm: a brace group after `||` is not read as an exit. `|| { echo no; exit 1; }` is refused, though the shell exits there and the write never runs.
- A git write that names its folder with `-C` is not refused, because `-C` does not depend on the `cd`.
- The refusal names no folder. Its remedy says to check the path, or to join the `cd` to the git command with `&&`.
- Protected by the cases in `tests/guard/s17500-conflict-markers.py` named "a cd into a missing folder, then ; add -A and commit, in a cwd repo whose edit is clean", with its control "a cd into an existing folder, then ; add -A and commit, in a cwd repo whose edit is clean". Red before the rule: 1 failed on the base commit 4680473b0c. The cases beside them cover add, push, merge, pull, rebase, cherry-pick, `--continue`, a commit after a newline, a mkdir, clone or worktree add of the folder, `|| exit 1` (passes), `|| return` (refused), and a status that passes.

Kind: process
Home: hooks/guard_merge.py
