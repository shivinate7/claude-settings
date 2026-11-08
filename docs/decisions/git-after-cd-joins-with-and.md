# A git write after a cd joins with `&&`

## The ruling

Rule `git-after-cd` in `hooks/guard.py` refuses a git write that follows a `cd` joined to it by `;`, a newline or `||`.

A write is one of these:

- A verb of `SESSION_HOME_GIT_VERBS`, `push` or `update-ref`.
- A file verb of `GIT_FILE_VERBS` (`rm`, `mv`).
- A `fetch` that writes a branch (`fetch_moves_branch`).
- A `branch` with a force, move or delete flag.
- A verb of `GIT_AFTER_CD_EXTRA_VERBS`: an `add` that is no dry run, a `tag` that names or deletes a tag, a `config` that sets or unsets a value (not `--get`, `--list` or a bare key), and `worktree add`. They are a second list because rule session-home pins `worktree add` as allowed.

A call whose argv names a read, such as `push --dry-run` or `push -n` (`read_verb`), is no write.

1. When the cd fails, the shell stays in its folder and a `;` runs the next command there. The write then lands in the primary checkout the session meant to leave alone.
2. The rule reads `cd_walk(...).stranded` for each write, with `failed_cd_stays=True`. A missing folder leaves the shell where it was, so `stranded` is true until a cd to a full path, home or `-` lands. `cd_walk(...).skipped` marks a segment that a failed `&&` chain never runs.
3. The refusal tells the session to join the cd to the write with `&&`, or to leave out the cd and use `-C` with a full path. It names no target.

Allowed forms:

- `cd X && git push`: a failed cd stops the chain. The skip covers a whole compound that follows the `&&`: a `{ ... }` group, an `if ... fi`, a `for`, `while` or `until` loop through `done`, across `;` and newlines, so `cd X && { git add -A; git commit -m m; }` passes. Every opener and closer in a segment counts, so nested ones do: `{ { git add; } }`, `{ for f in a; do git add; done }`. A closer with a redirect attached counts once (`}>/dev/null`, `done>/dev/null`). A word counts only as the shell reads it: a quoted `"done"`, `echo "done }"` and `done_x` open and close nothing. The skip ends when the compound closes: a `;` or newline after it runs in the stranded folder, so `cd X && { git add -A; }; git push` is refused. A `case` is not read, so the skip ends at its first `;`.
- `if ! cd X; then exit 1; fi; git push`: the test passes when the cd fails, `exit` runs, and the shell ends. The `then` body must start with a bare `exit`. With any other first command, as `then echo no`, the write after `fi` is refused.
- `set -e; cd X; git push`: under `set -e` a failed cd that stands alone, ending in `;` or a newline, ends the shell. `set -eu`, `set -o errexit` and a `set -e` on its own line count, but only a `set -e` sure to run: a top-level segment, first word `set`, not inside a `{ }`, `if`, loop, `case` or function body or a `( )`, not after `&&` or `||`, not piped or in the background. Any `set +e` (or `+o errexit`) before the cd turns it off again, wherever it stands, even in a function nothing calls. A cd before or after `&&`, `||` or `|` (it may never run), inside `( ... )`, or inside a group, `if` or loop, does not count as the exit. The same holds for the `if ! cd X; then exit` form after `&&` or `||`. Options end at the first word that is not one, so `set -- -e` and `set -- ""` set nothing.
- `cd X || exit 1; git push`: the shell exits when the cd fails. The `exit` is read as the first command after the `||`, bare or as a `;`-joined step of a `{ ... }` group. A top-level `return` does not stop bash, so `cd X || return 1; git push` is refused. So are `cd X || (exit 1); git push`, because a subshell's `exit` ends only the subshell, and an `exit` in a pipe, as `cd X || exit 1 | cat; git push` or `cd X || { exit 1; } | cat; git push`.
- `if cd X; then git push; fi`: the `then` body runs only when the cd landed. An `else` body and the commands after `fi` run in the stranded folder and are refused.
- `git -C /full/path push`, with or without a cd before it. A `-C` that holds a variable is unknown and passes.
- A read: `status`, `log`, `branch -l`, `stash list`, `tag -l`, `config --get`.
- A cd inside `( ... )`: its scope ends at the `)`. The folder it names is read without the `)`. The shell outside is still stranded after the `)`, so `cd X; (cd /tmp) && git push` is refused, and `cd X; (cd /tmp && git push)` passes, because the chain inside runs in `/tmp`.
- A cd that lands, or a cd whose word holds a variable: the folder is known or unknown, never stranded.
- A cd, a git word or a comment opener inside quotes or after `#`.

Risk kind: incident 2026-11-07 ~16:15 CST. A session ran `cd <gone worktree> && <vcs> status; <vcs> fetch; <vcs> checkout -B ...; <vcs> merge ...`. The cd failed, so the `;`-joined writes ran in the primary checkout.

Reproduction: `cd /tmp/w/b-int && <vcs> status --short; <vcs> fetch origin; <vcs> checkout -B claude/int-batch-banchi-1107b origin/main; <vcs> merge --no-ff claude/lane-a` -> allowed on main 174b005c1; the checkout -B and merge ran in the primary checkout

Limits:

- A cd that fails only at run time, not at check time, is not seen. A folder that exists when the guard looks is trusted.
- A relative `-C` joins onto the stranded folder, so it is refused; a `-C` that holds a variable is not read.
- A segment the tokenizer cannot read, because a quote is cut in it, is unknown and passes. An interpreter's heredoc body is read this way.
- A cd into a folder an earlier `;` segment creates is refused: `mkdir -p X; cd X; git commit` and `git worktree add ../x; cd ../x; git commit`. The folder is not there when the guard looks. The `&&` form passes.
- A cd to a variable is not judged: `cd "$WT"; git push` passes. Failing closed would also refuse `cd "$REPO"; git status` in normal work. Debt `git-after-cd-variable-cd` holds the gap.
- An `|| exit` is read only as the first command after the `||`, or a `;`-joined step of a `{ ... }` group. An `exit` behind an `&&` inside the group, or in a function, is not read, so the write after it is refused. `cd M || { echo a && exit 1; }; git push` is refused though bash exits first. The rule fails closed, and the `&&` remedy passes.
- errexit fails closed, so these are refused though bash exits first: a `set -e` inside a group, `if`, loop, function or `( )` (`{ set -e; }; cd X; git push`, `f() { set -e; }; f; cd X; git push`), a `set -e` after `&&` or `||` (`true && set -e; cd X; git push`), and a failed cd inside a group under `set -e` (`set -e; { cd X; }; git push`). A `set +e` anywhere, in dead code too, turns errexit off. Only the opener and closer words are read: `case` and `esac`, `select` and a function's `{` count for errexit only, and a function that is called is not followed.
- The compound count takes a word that starts with a quote as text (`_quoted_opens`). A keyword quoted after its first character, `i"f"`, reads as the keyword. When the two readings of a segment differ in word count, no word is marked, so a quoted `"{"` at the head of such a segment opens a compound.
- A crash in `cd_walk` read with `failed_cd_stays` reads as stranded, so the write is refused, and a `guard-crash` line is logged. The guard otherwise fails open on a crash.
- `echo x | ( cd X; push )` and `cd X || { push; exit 1; }` are not read as stranded cases.
  Fix: none — a pipe into a subshell cd, or a push inside the || block, is not a form Claude writes by mistake (guard-guards-mistakes-only). Until: 2026-11-21
- `f() { cd M; push; }; f`, `function f { cd M; push; }; f` and `case x in x) cd M; push;; esac` are not read: a cd inside a function body or a case arm.
  Fix: none — a cd and a push inside one function body or case arm is not a form Claude writes by mistake (guard-guards-mistakes-only). Until: 2026-11-21
- An `if` is read only when the cd is the whole test and the next segment opens the `then`. `if cd X && Y; then`, `while cd X; do` and `elif` are not read, so the write in their body is refused.
- A `tag` is a read when it holds a listing flag (`-l`, `--contains`, `--points-at`, `--merged`, `--sort`) or no word. A `config` is a write when it names a key and a value, or holds a write flag. A `worktree` verb other than `add` is not a write here: `worktree remove` and `prune` are judged by their own rules.
- A quoted `>` in an `echo` is text, not a redirect (rule conflict-markers, `_chain_safe`). A backtick or `$(` inside it still counts as a step that may change the tree.
- PowerShell is out of scope. The lane brief named Bash, and `cd_walk` reads Bash joins.
- An `sh -c` body is not walked (`guard-guards-mistakes-only`).

Kind: process
Home: rule:shared-trees-confirm-before-write
