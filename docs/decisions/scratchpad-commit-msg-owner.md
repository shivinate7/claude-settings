# An agent commits the message it wrote itself, never a file from the shared scratchpad

## The ruling

The guard refuses a `git commit` from an agent's call when a `-F` or `--file` message file (not `-`) resolves, by real path, into any session's scratchpad.

- The agents of one session share its scratchpad folder, and an agent's session id is its parent's. A file there may hold another agent's message.
- The path alone decides. The file's text, the session id in the path and a missing session id on the call change nothing. A link is judged by the file it resolves to.
- `hooks/guard.py` `scratchpad_commit_file` reads the files `message_sources` names, so every flag form is covered: `-F x`, `-Fx`, `-aF x`, `--file x`, `--file=x`, and `--amend`.
- A commit that a wrapper runs is judged the same way: `bash -c '...'`, `sh -c "..."`, `sh -lc`, and the other wrappers `inner_commands` reads. `scratchpad_commit_file` walks the wrapped text with `inner_commands`, from the directory the wrapper runs in, so a `cd` inside the wrapper sets the folder for a relative path. Echoed text is no command and passes.
- A relative path is read from the directory the shell is in when the commit runs: `dir_before_segment` (cd, pushd), then the call's own `-C`. When that directory cannot be told, only an absolute path is judged.
- A variable that the same command binds to literals (`S=<path>; ... -F $S/msg`) is expanded with `_rm_values`. Any other variable, such as `$HOME/x`, stays as the environment gives it.
- The gate is the guard's agent flag: a truthy `agent_id` or `agent_type`. An orchestrator's payload (both null) passes. A main session started with `--agent` that carries `agent_type` alone is refused too (unmeasured); its cost is one retry with `-F -` or `-m`. Same widening as debt note `kill-tag-agent-flag-widened`.
- Allowed: `-F -` with a heredoc, `-m`, a file outside every scratchpad, and a `gh pr create --body-file`. The remedy names `-F -` and `-m`.
- Named gaps, not refused: a glob in the file name, and a file read through `$(cat <file>)`. Stdin from a scratchpad file is a gap too: `-F - < file` and `cat file | git commit -F -`. So are a variable the command binds in a way `_rm_values` cannot read, and a relative path after a `cd` the guard cannot follow. A commit inside a command substitution, `echo $(git commit -F <file>)`, is a gap too. A variable bound outside a wrapper and used inside `bash -c` is refused although the inner shell may not see it: one retry.
- The check runs inside the existing guard call: no process start, no file written.

Mistake it stops: an agent committed another agent's message file from the shared scratchpad.
Harm: the commit carries a message that describes another agent's work.

Protected by the `scratchpad-message` family in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py
