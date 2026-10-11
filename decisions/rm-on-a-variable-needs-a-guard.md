# rm on a variable path needs a `:?` guard

## The question

How do bypass-mode sessions stop waiting on the owner for Claude Code's critical-path `rm`
prompt?

## The ruling

Owner, 2026-10-11 ("Ship guard now, hook later"):

1. Rule `rm-var-unguarded` in `hooks/guard.py` refuses a recursive `rm` when a target has an
   unguarded variable expansion followed by `/`, such as `rm -rf $S/$d` or `rm -rf "$D"/*`.
   The refusal prints the flagged targets with each expansion written `${NAME:?}`. The agent
   retries. The owner sees no prompt.
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

- `$HOME`, `$PWD`, and a variable whose assigned or loop value expands `~`, `$HOME`, `${HOME…}`,
  `$PWD`, or a `pwd` command in `$(…)` or backticks (any flags or path), stay a prompt. The docs say a `:?` guard does not clear
  them. The guard refuses them also when guarded. The remedy tells the agent to name the one
  directory it means as a literal path. The remedy never computes that path, because a computed
  path such as `/Users/<you>/*` could wipe the home folder.
- A home path read another way, such as `D=$(getent passwd $USER | cut -d: -f6)`, is not seen.
  Nor is a chained copy, such as `H=$HOME; X=$H`.
- A bare `$HOME` target is refused by rule `destructive-delete`. The brace forms `${HOME}` and
  `${HOME:?}` are not, so Claude Code's own prompt stays the backstop.
- The taint is read by variable name across the whole command. A later reassignment, or a
  `D=$HOME` inside quoted text, still taints `D`. This is a rare false alarm.
- An escaped `\$S/x` gets a hit, although the shell reads it as literal. This is a rare false
  alarm.
- These forms are not seen, so Claude Code's own prompt stays the backstop:
  - an `rm` inside a script file, a heredoc piped to `sh`, or `sh -c` nested 5 deep;
  - `exec rm`, `timeout 5 rm`, `nice -n 5 rm`, `! rm`, `(rm …)`, `$(rm …)`, backtick `rm`,
    `find -exec rm`, and `$cmd -rf`;
  - `$S'/'*`, `$S\/*`, `${S:-}/*`, `$S*`, and `rm -rf $(pwd)/dist`.
