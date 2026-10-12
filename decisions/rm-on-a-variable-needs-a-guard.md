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
     - Home and the cwd are compared after `realpath`, and case-folded on macOS.
   - If the guard cannot read a target, the refusal gives the literal-path reason. A read error
     never lets a command through unjudged.
   - Otherwise: name the one directory as a literal path. This covers inherited names such as
     `$OLDPWD`, positionals, `read` loops, and every other binding. The remedy never computes a
     path, because a computed path such as `/Users/<you>/*` could wipe the home folder.

   The agent retries. The owner sees no prompt. This is an allow-list. A deny-list of unsafe
   sources took seven review rounds and still missed classes.
2. A hook that answers the `rm` prompt is deferred to its own change. See deferred item
   rm-prompt-answer-hook. The first build allowed deletes of the home folder, `*`, `{~,x}` and
   `..` escapes, in every mode.
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
