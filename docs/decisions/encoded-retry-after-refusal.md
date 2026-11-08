# A refused command is not sent again in an encoded form

## The ruling

The `encoded-retry-after-refusal` rule in `hooks/guard_encoded.py` refuses a Bash call when both hold:

- The call decodes text and runs it, or its command word is built from escapes:
  - a decode piped into a shell (`base64 -d`, or `printf` or `echo -e` with hex, octal or unicode escapes, piped to `sh`, `bash`, `zsh`, `dash` or `ksh` with no `-c`);
  - `eval`, `source` or `.` of a command substitution that decodes;
  - a command word that is an ANSI-C `$'...'` word with an escape, or a command substitution that decodes.
- Its own session had a refusal in the last ten minutes: a row in the session's refusal state file, or a guard.log deny row of the session.

A state row that names an agent counts only for that agent's calls. A row that names none counts for the whole session. A guard.log row names no agent, so it counts for the whole session, the orchestrator included.

An orchestrator call with no agent id is allowed when the only fresh row names an agent.

Passes:

- A decode into a variable, a file or `jq`.
- `printf` with a colour escape and no pipe to a shell.
- `$'...'` in an argument.
- Text in quotes, a comment or a heredoc body.
- Any call with no refusal in the window, and any PowerShell call.

The state is read only after the call's shape matches, so an ordinary call costs no file read, no new file, no log and no process. The clock is `local_time.clock()`.

The refusal tells the agent to report and does not name the form as a remedy. The same line goes to every agent brief (`hooks/agent_brief.py`), and each agent file that says a refusal is final adds the command case.

Mistake it stops: an agent met a refusal of a command, then sent the same command spelled with escapes or base64. The refusal had already said the act was not allowed, so the encoded form is the same act.

Outcome protected: a refusal stays final, so the owner or the orchestrator decides the next step.

False-alarm cost: an ordinary decode into a shell within ten minutes of an unrelated refusal in the same session is refused once, and the agent reports. An override lifts it. A guard.log deny from one agent brakes the orchestrator's own decode-and-run for ten minutes (accepted, the log names no agent).

Not read: an `eval` or `bash -c` whose argument is itself an ANSI-C word, a decode through `openssl`, `xxd` or a language runtime, and a glob spelling of a command word.

Kind: process
Home: hooks/guard_encoded.py
