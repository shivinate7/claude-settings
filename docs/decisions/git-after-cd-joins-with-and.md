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

The rule also refuses a `git push` that runs after a `;`- or newline-joined command whose failure the push cannot see, with or without a cd (coordinator step push-after-check-semicolon, 2026-11-08 09:51 CST; lane pick 2026-11-08 10:38 CST, which replaced the pick of 10:01 CST). A failed check does not stop a push joined to it by `;` or a newline. Incident 2026-11-08, PR #2098: a check and a push were joined by `;`, and the push ran after the check failed. The refusal tells the session to join the commands with `&&`. `git_push_after_check_hit` reads the same segments and ends as `git_after_cd_hit`.

The push check walks back from the push:

1. It goes back over the push's `&&` chain to the chain's start. A `||` or `|` before that start is no `;` join, so the push passes. One exception: when the chain before the push is only print steps (`echo`, `printf`, `true`, `:`), the `||` hides the check's failure, since the print succeeds and the `&&` goes on to the push. `pytest -q || echo x && git push` is refused. `pytest -q || exit 1 && git push` and `cd X || echo x && git push` pass (the first stops the shell, the second has no check before the `||`). A line that ends in `&&`, `||` or `|` joins the next line by that operator, not by the newline.
2. If a `;` or a newline stands before that start, it looks at the command before it.
3. A cd, `exit`, `set`, `true`, or an `export` or `echo` whose words run no substitution (or a group or `if` made only of them) is skipped, and the walk goes on from it over its own `&&` chain. That chain must be inert too, so `pytest -q && cd X; git push` is refused.
4. A lone command after a `set -e` sure to run is skipped too, since its failure ends the shell. The lone command stands at the top level, outside any group, `if`, loop or `( )`, and outside any `&&` or `||` list, pipe, `!` or `&`. So `set -e; pytest -q; git push` passes, and `set -e; pytest -q && true; git push` is refused.
5. A command that exits on failure protects itself and the whole `&&`, `||` or `|` list before it, and nothing before that list: `pytest || exit 1`, `pytest || { echo bad; exit 1; }` and `if ! pytest; then exit 1; fi` pass when nothing stands before them. The walk goes on back past them, so `pytest -q; <fetch> || exit 1; <push>` is refused, with a fetch and a push in the two places. Only a bare `exit` counts: `|| return` and `|| (exit 1)` do not stop the shell, and neither does an `exit` inside a `( )` group, as in `( pytest -q || exit 1 ); git push`, `( pytest -q || { echo bad; exit 1; } ); git push` and `( if ! pytest -q; then exit 1; fi ); git push`. The `if !` body may stand on the lines after the test, and may print before it exits: `if ! pytest -q; then echo bad; exit 1; fi` passes on one line or over three. Only `echo`, `printf`, `true` and `:` with no pipe or `||` count as that print, and a substitution in it is fine, since the step's status is its own: `if ! pytest -q; then echo "$(date)"; exit 1; fi` passes. A step joined to the exit by `&&` counts only when it has no redirect, since a failed redirect skips the exit: `then echo bad > /no/dir && exit 1` is refused. An fd copy (`>&2`, `2>&1`, `>&-`) opens no file and is no redirect here: `then echo bad >&2 && exit 1` passes (lane pick 2026-11-08 14:34 CST). A redirect on a `;`-joined print is fine. A substitution the split cut open (`echo $(a; exit 1)`) is no print step. Any other step, and an `exit` after `else`, `elif` or `fi`, is no exit tail.
6. The test of the compound that holds the push guards the body, and nothing before the compound. The body opener (`then`, `do`, `else`, `elif`) may stand on the push's line or on the line before it. The walk goes on back past the compound's head (`if`, `for`, `while`, `until`) to any earlier `;`-joined check: `pytest -q; for r in a b; do git push; done`, `pytest -q; until false; do git push; done`, `pytest -q; if <fetch>; then <push>; fi` and a push in an `elif` or `else` body are refused. With nothing before the compound the push passes, as in `if pytest -q; then git push; fi`. A `fi` or `done` between them closes that body, so `if pytest; then :; fi; git push` is refused.
7. A group opener `{` or `(` is walked into. So `{ pytest -q; git push; }`, `( pytest -q; git push )` and `cd X && { pytest -q; git push; }` are refused. The opener is read past when a compound stands inside it: `pytest -q; { for r in a b; do git push $r; done; }` and `pytest -q; ( if true; then git push; fi )` are refused, since the compound's own test covers only its body.
8. Any other command refuses, a subshell `( ... )` included: `cd X; (pytest -q); git push` is refused.

Forms the push check passes:

- A push with nothing before it, or with only skipped commands before it: `cd X; git push`, `set -e; cd X; git push`, `cd X || exit 1; git push`, `if ! cd X; then exit 1; fi; git push`.
- A push that starts a compound body, on the opener's line or on the next one: `if pytest; then git push; fi`, `while pytest; do\n  git push\ndone`.
- A chain joined by `&&` over lines: `pytest -q &&\ngit push`.
- A `--dry-run` push, a read.
- A check joined to the push by `&&` alone.

A `git add`, `git commit` or other command before the `;` is not skipped, so `git commit -m m; git push` is refused.

Allowed forms:

- `cd X && git push`: a failed cd stops the chain. The skip covers a whole compound that follows the `&&`: a `{ ... }` group, an `if ... fi`, a `for`, `while` or `until` loop through `done`, across `;` and newlines, so `cd X && { git add -A; git commit -m m; }` passes. Every opener and closer in a segment counts, so nested ones do: `{ { git add; } }`, `{ for f in a; do git add; done }`. A closer with a redirect attached counts once (`}>/dev/null`, `done>/dev/null`). A word counts only as the shell reads it: a quoted `"done"`, `echo "done }"` and `done_x` open and close nothing. The skip ends when the compound closes: a `;` or newline after it runs in the stranded folder, so `cd X && { git add -A; }; git push` is refused. A `case` is not read, so the skip ends at its first `;`.
- `if ! cd X; then exit 1; fi; git push`: the test passes when the cd fails, `exit` runs, and the shell ends. The `then` body must reach a bare `exit` through steps that only print (`echo`, `printf`, `true`, `:`): `if ! cd X; then echo bad; exit 1; fi; git push` passes. With any other step first, as `then make x; exit 1`, or no exit, as `then echo no`, the write after `fi` is refused.
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

- A redirect to a file before `&&` in an `if !` body ends the exit tail, `>/dev/null` included, though bash exits first when the file opens. The rule fails closed; a `;` join in place of the `&&` passes. An fd copy (`>&2`, `2>&1`, `>&-`, `FD_COPY`) opens no file and cannot fail, so `then echo bad >&2 && exit 1` passes.
- `A || echo x && push` is refused only when every step between the `||` and the push is a print step. `A || make x && push` passes, as any `||` before a push's chain did. Also not read: a `cd` as the whole left side (`cd X || echo x && push`), which `git_after_cd_hit` judges.
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
