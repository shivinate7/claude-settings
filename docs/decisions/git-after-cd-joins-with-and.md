# A git write after a cd joins with `&&`

## The ruling

Rule `git-after-cd` in `hooks/guard.py` refuses a git write that follows a `cd` joined to it by `;`, a newline or `||`.

A write is one of these:

- A verb of `SESSION_HOME_GIT_VERBS`, `push` or `update-ref`.
- A file verb of `GIT_FILE_VERBS` (`rm`, `mv`).
- A `fetch` that writes a branch (`fetch_moves_branch`).
- A `branch` with a force, move or delete flag.

A call whose argv names a read, such as `push --dry-run` or `push -n` (`read_verb`), is no write.

1. When the cd fails, the shell stays in its folder and a `;` runs the next command there. The write then lands in the clone the session meant to leave alone.
2. The rule reads `cd_walk(..., failed_cd_stays=True)` once for each write. A missing folder leaves the shell where it was. A write is refused when the walk says `stranded`: a cd that failed ran ahead of it and the shell is still where it stayed.
3. The refusal tells the session to join the cd to the write with `&&`, or to leave out the cd and use `-C` with a full path. It names no target.

Allowed forms:

- `cd X && git push`: a failed cd stops the chain.
- `git -C /full/path push`, with or without a cd before it. A `-C` that holds a variable is unknown and passes.
- A read: `status`, `log`, `branch -l`, `stash list`.
- A cd inside `( ... )`: its scope ends at the `)`.
- A cd that lands, or a cd whose word holds a variable: both reads agree.
- A cd, a git word or a comment opener inside quotes or after `#`.

Risk kind: incident 2026-11-07 ~16:15 CST. A session ran `cd <gone worktree> && <vcs> status; <vcs> fetch; <vcs> checkout -B ...; <vcs> merge ...`. The cd failed, so the `;`-joined writes ran in the primary checkout.

Reproduction: `cd /tmp/w/b-int && <vcs> status --short; <vcs> fetch origin; <vcs> checkout -B claude/int-batch-banchi-1107b origin/main; <vcs> merge --no-ff claude/lane-a` -> allowed on main 174b005c1; the checkout -B and merge ran in the main clone

Limits:

- A cd that fails only at run time, not at check time, is not seen. A folder that exists when the guard looks is trusted.
- A relative `-C` joins onto the stranded folder, so it is refused; a `-C` that holds a variable is not read.
- A segment the tokenizer cannot read, because a quote is cut in it, is unknown and passes. An interpreter's heredoc body is read this way.
- A cd into a folder an earlier `;` segment creates is refused: `mkdir -p X; cd X; git commit` and `git worktree add ../x; cd ../x; git commit`. The folder is not there when the guard looks. The `&&` form passes.
- A cd to a variable is not judged: `cd "$WT"; git push` passes. Failing closed would also refuse `cd "$REPO"; git status` in normal work. Debt `git-after-cd-variable-cd` holds the gap.
- PowerShell is out of scope. The lane brief named Bash, and `failed_cd_stays` in `cd_walk` reads Bash joins.
- An `sh -c` body is not walked (`guard-guards-mistakes-only`).

Kind: process
Home: rule:shared-trees-confirm-before-write
