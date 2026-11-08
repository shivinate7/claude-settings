# An agent commits the message it wrote itself, never a file from the shared scratchpad

## The ruling

The guard refuses a `git commit` from an agent's call when a `-F` or `--file` message file (not `-`) resolves, by real path, into any session's scratchpad.

- The agents of one session share its scratchpad folder, and an agent's session id is its parent's. A file there may hold another agent's message.
- The path alone decides. The file's text, the session id in the path and a missing session id on the call change nothing. A link is judged by the file it resolves to.
- `hooks/guard.py` `scratchpad_message_file` reads the files `message_sources` names, so every flag form is covered: `-F x`, `-Fx`, `-aF x`, `--file x`, `--file=x`, and `--amend`.
- Allowed: an orchestrator's call (no `agent_id`), `-F -` with a heredoc, `-m`, a file outside every scratchpad, and a `gh pr create --body-file`. The remedy names `-F -` and `-m`.
- The check runs inside the existing guard call: no process start, no file written.

Mistake it stops: an agent committed another agent's message file from the shared scratchpad.
Harm: the commit carries a message that describes another agent's work.

Protected by the `scratchpad-message` family in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py
