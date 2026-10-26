# rm on a variable path needs a `:?` guard

## The ruling

Bypass-mode sessions must not wait on the owner for Claude Code's critical-path `rm` prompt (owner ruling 2026-10-11). In bypass mode no allow rule clears that prompt, but a removal with every expansion guarded `${NAME:?}` runs without one, and a `PermissionRequest` hook can answer the prompt that remains.

1. Rule `rm-var-unguarded` in `hooks/guard.py` refuses a recursive `rm` only in the shape Claude Code prompts on: a variable, then `/`, then a glob, another variable, a slash, a quote, or the end. Examples: `rm -rf $S/$d`, `rm -rf "$D"/*`, `rm -rf $D/`. So `rm -rf "$ROOT/dist"` is not refused. A `..` right after the variable, as in `rm -rf "$S"/../*`, is refused with the literal-path reason, because it can empty the cwd. The refusal offers one of two remedies:
   - `${NAME:?}`, only when the guard can see that each such name is safe. Safe means that each binding of the name in the command is `NAME=<literal>`, `for NAME in <literal words>`, or `NAME=$(mktemp …)`. A literal does not start with `.`, and holds no `..`, `~`, `$`, backtick or glob. With the values put in, the target is not `/`, home, a home parent, the cwd or a cwd parent, and not a glob directly under one of them. The command holds no `cd`, `pushd` or `popd`. The other conditions are in `hooks/guard_rm_var.py`.
   - Otherwise: name the one directory as a literal path. This covers inherited names such as `$OLDPWD`, positionals, `read` loops, and every other binding. The remedy never computes a path, because a computed path such as `/Users/<you>/*` could wipe the home folder.

   If the guard cannot read a target, the refusal gives the literal-path reason. A read error never lets a command through unjudged. The agent retries, and the owner sees no prompt. This is an allow-list, because a deny-list of unsafe sources missed classes through many review rounds.
2. `hooks/rm_prompt_answer.py`, a `PermissionRequest` hook on Bash, answers the prompt that remains. It answers allow only when all of these hold:
   - The session is in bypass mode: `permission_mode` is `bypassPermissions`.
   - The command is only assignments and `rm` calls.
   - Each `rm` target is one `${NAME:?}` expansion followed only by plain folder names. No `..`, glob, brace, `~`, `$HOME`, `$PWD`, second expansion or substitution.
   - Each NAME is assigned once, in the same command, to a literal. `_rm_target_bad` in `hooks/guard.py` says the literal is not a critical path. That function is the one home.
   - The command binds no other name. `IFS` and `PATH` are refused outright, bound or expanded: a bound `IFS` splits an unquoted expansion into two targets, and a bound `PATH` picks the `rm` that runs.

   Every other request prints nothing. The prompt reaches the owner unchanged. These still prompt, on purpose:
   - the `for d in …; do rm -rf "${S:?}/${d:?}"; done` form;
   - `export S=`, a value set twice, `/bin/rm`, `command rm`, `rm --recursive`;
   - a redirect, `|| true`, `&`, a trailing slash on the target, and a prefix assignment `S=x rm`.

   A non-recursive `rm "${S:?}"/a` is allowed.
3. A bare variable target, such as `rm -rf "$d"`, is not refused. Claude Code does not treat it as a critical path.

Kind: process
Home: hooks/guard.py
