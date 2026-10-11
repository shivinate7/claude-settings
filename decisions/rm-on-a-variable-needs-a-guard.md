# rm on a variable path needs a `:?` guard

## The question

How do bypass-mode sessions stop waiting on the owner for Claude Code's critical-path `rm`
prompt?

## The ruling

Owner, 2026-10-11 ("Both"):

1. Rule `rm-var-unguarded` in `hooks/guard.py` refuses a recursive `rm` when a target has an
   unguarded variable expansion followed by `/`, such as `rm -rf $S/$d` or `rm -rf "$D"/*`.
   The refusal prints the same command with each expansion written `${NAME:?}`. The agent
   retries. The owner sees no prompt.
2. `hooks/rm_prompt_answer.py` is a `PermissionRequest` hook on Bash. It answers allow only
   when each `rm` in the command meets all of these conditions:
   - every variable expansion has a `:?` guard;
   - no target has a command substitution or `$HOME`;
   - no target is a literal critical path.

   Every other request goes on to the owner unchanged.
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

- `$HOME` and a variable set from `$(pwd)` stay a prompt. The docs say a `:?` guard does not
  clear them. The remedy names a literal path.
- An `rm` inside a script file is not seen.
