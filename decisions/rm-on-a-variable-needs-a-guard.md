# rm on a variable path needs a `:?` guard

## The question

How do bypass-mode sessions stop waiting on the owner for Claude Code's critical-path `rm`
prompt?

## The ruling

Owner, 2026-10-11 ("Ship guard now, hook later"):

1. Rule `rm-var-unguarded` in `hooks/guard.py` refuses a recursive `rm` only in the shape
   Claude Code prompts on: a variable, then `/`, then a glob, another variable, a slash, a
   quote, or the end. Examples: `rm -rf $S/$d`, `rm -rf "$D"/*`, `rm -rf $D/`. Owner,
   2026-10-11 ("Only where Claude Code prompts"). So `rm -rf "$ROOT/dist"` is not refused.
   A `..` right after the variable, as in `rm -rf "$S"/../*`, is refused with the literal-path
   reason, because it can empty the cwd.
   The refusal offers one of two remedies:
   - `${NAME:?}`, only when the guard can see that each such name is safe. Safe means that each
     binding of the name in the command is `NAME=<literal>`, `for NAME in <literal words>`, or
     `NAME=$(mktemp …)`. A literal does not start with `.`, and holds no `..`, `~`, `$`,
     backtick or glob. With the values put in, the target is not `/`, home, a home parent, the
     cwd or a cwd parent. It is also not a glob directly under one of them. The command holds no `cd`, `pushd` or
     `popd`. More conditions apply:
     - The variable starts the target word.
     - A literal holds no whitespace or brace.
     - Each binding comes before the `rm` and is not a prefix assignment such as `X=/tmp rm …`.
       A binding after an `sh -c`, `bash -c` or `eval` that holds the `rm` also blocks `:?`.
     - A `mktemp` value has nothing after the `)`.
     - Home and the cwd are compared after `realpath`, and case-folded on macOS and Windows.
       On Windows a Git Bash drive spelling such as `/c/Users/<you>` is read as `C:/Users/<you>`
       first (found by review, 2026-10-12).
   - If the guard cannot read a target, the refusal gives the literal-path reason. A read error
     never lets a command through unjudged.
   - Otherwise: name the one directory as a literal path. This covers inherited names such as
     `$OLDPWD`, positionals, `read` loops, and every other binding. The remedy never computes a
     path, because a computed path such as `/Users/<you>/*` could wipe the home folder.

   The agent retries. The owner sees no prompt. This is an allow-list. A deny-list of unsafe
   sources took seven review rounds and still missed classes.
2. `hooks/rm_prompt_answer.py`, a `PermissionRequest` hook on Bash, answers the prompt that
   remains. Built 2026-10-12 (brief step 7, one Opus agent on the owner's word). It answers
   allow only when all of these hold:
   - The session is in bypass mode: `permission_mode` is `bypassPermissions`.
   - The command is only assignments and `rm` calls.
   - Each `rm` target is one `${NAME:?}` expansion followed only by plain folder names. No `..`,
     glob, brace, `~`, `$HOME`, `$PWD`, second expansion or substitution.
   - Each NAME is assigned once, in the same command, to a literal. `_rm_target_bad` in
     `hooks/guard.py` says the literal is not a critical path. That function is the one home.
   - The command binds no other name, and the names `IFS` and `PATH` are refused outright,
     bound or expanded. A bound `IFS` splits an unquoted expansion into two targets, even when
     `IFS` is the target's own name, and a bound `PATH` picks the `rm` that runs (found by
     review, 2026-10-12, three rounds).

   Every other request prints nothing, so the prompt reaches the owner unchanged. The cases
   are in `hooks/test_rm_prompt_answer.py` (104). Named limits, silent on purpose: the
   incident's `for d in …; do rm -rf "${S:?}/${d:?}"; done` form, 5 of the 7 incident prompts,
   still prompts. So do `export S=`, a value set twice, `/bin/rm`, `command rm`,
   `rm --recursive`, a redirect, `|| true`, `&`, a trailing slash on the target, and a prefix
   assignment `S=x rm`. A non-recursive `rm "${S:?}"/a` is allowed. No mutation anchor covers
   the hook module. The first build (18fddf9) allowed deletes of the home folder, `*`, `{~,x}`
   and `..` escapes, in every mode. Those four inputs are red cases now.
3. A bare variable target, such as `rm -rf "$d"`, is not refused. Claude Code does not treat
   it as a critical path.

## The incident

2026-10-10 to 10-11, Claude Code 2.1.295, measured over all transcripts: 24 Bash prompts. 7
were `rm` on a `$var` path, 5 of them `S=…; for d in …; do rm -rf $S/$d`. The sessions ran in
bypass mode, where no allow rule clears this prompt. The permission-modes docs say a removal
with every expansion guarded `${NAME:?}` "runs without a prompt" in bypass mode, and that "a
`PermissionRequest` hook can answer the prompt".

The same count found that 232 of the 246 "allow once" records were answers to
`AskUserQuestion`, not Bash prompts.

## Named limits

- A bare `$HOME` target is refused by rule `destructive-delete`. The brace forms `${HOME}` and
  `${HOME:?}` are not, so Claude Code's own prompt stays the backstop.
- An escaped `\$S/x` gets a hit, although the shell reads it as literal. This is a rare false
  alarm.
- These forms are not seen, so Claude Code's own prompt stays the backstop:
  - an `rm` inside a script file, a heredoc piped to `sh`, or `sh -c` nested 5 deep;
  - `exec rm`, `timeout 5 rm`, `nice -n 5 rm`, `! rm`, `(rm …)`, `$(rm …)`, backtick `rm`,
    `find -exec rm`, and `$cmd -rf`;
  - `$S'/'*`, `$S\/*`, `${S:-}/*`, `$S*`, and `rm -rf $(pwd)/dist`;
  - `${D[0]}`, `${!D}`, `${D%…}` and zsh `$D:h`.
