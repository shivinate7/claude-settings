# /safe-stop queues one prompt

## The ruling

`/safe-stop` is a command of the session-board mod (`session-board-mod-limits`, session-board keeps small records).

- `/safe-stop` refuses non-user origins by a block-list in `hooks/lib.mjs`. Other origins run, including `unclassified`.
- It asks the installed handoff hook for its path functions. A run makes the handoff folder. A plan makes none.
- It sends this session one prompt with `$.prompt.submit`. The prompt tells the session to finish or park its step and to start no new work or agent. The session follows the hook's prompt file, rewrites the handoff whole, and replies with one line: branch, uncommitted files, unpushed commits and running agents. The session writes the handoff. The mod writes none.
- The reply says the prompt is queued until the session is idle, or "could not send" if the host drops it. An over-long path is refused, not cut.
- `/safe-stop plan` prints the prompt and sends nothing.

Kind: process
Home: mods/session-board/hooks/lib.mjs
