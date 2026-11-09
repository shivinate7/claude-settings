# A refused command is not sent again in an encoded form

## The ruling

The `encoded-retry-after-refusal` rule in `hooks/guard_encoded.py` refuses a Bash call when both hold:

- The call decodes text and runs it, or its command word is built from escapes:
  - a decode piped into a shell with no `-c`. A decode is `base64 -d`, `printf` or `echo -e` with an escape, or `echo` of an ANSI-C `$'...'` word. The shell may sit in a subshell, as `(sh)`;
  - a shell handed decoded text as its script. The script is the word after `-c`, a process substitution `<(...)`, a herestring, or the file its stdin reads, as `sh < <(...)`. It holds a substitution that decodes, or a variable set from one earlier in the call;
  - `eval`, `source` or `.` of such a substitution or variable;
  - a command word that is an ANSI-C `$'...'` word with an escape, a substitution that decodes, or a variable set from one;
  - the decode forms above inside the script text of `sh -c` or `eval`, and inside any substitution: `$(...)`, backticks, `<(...)` or `>(...)`.

  A variable is set from a decode by `NAME=$(...)`, alone or after `export`, `declare`, `local`, `readonly` or `typeset`.
- Its own session had a refusal in the last ten minutes: a row in the session's refusal state file, or a guard.log deny row of the session.

A state row that names an agent counts only for that agent's calls. A row that names none counts for the whole session. A guard.log row names no agent, so it counts for the whole session, the orchestrator included.

An orchestrator call with no agent id is allowed when the only fresh row names an agent.

Passes:

- A decode into a variable, a file or `jq`.
- `printf` with a colour escape and no pipe to a shell.
- `$'...'` in an argument.
- Text in quotes, a comment or a heredoc body.
- Any call with no refusal in the window, and any PowerShell call.

The state is read only after the call's shape matches, so an ordinary call costs no file read, no new file, no log and no process. The clock is `local_time.clock()`. The shape read is linear in the call's length.

The guard.log rows are read through `lint/guard_log_report.py`. The rule finds `lint/` by walking up from `guard_encoded.py`, so it works in a repo (`hooks/` beside `lint/`) and in a copy install (`hooks/guard.d/<id>/`, with `lint/` beside `hooks/`).

The guard.log read covers only the last 256 KB (`LOG_TAIL_BYTES`, `hooks/guard_encoded.py`), so a fresh deny buried under more than 256 KB of later rows is missed.

The rule's own deny row in guard.log re-arms the ten-minute window, so a retry after its own refusal is refused again.

A fault in the shape read fails this rule open and no other. The guard's later rules still judge the call.

The refusal tells the agent to report and does not name the form as a remedy. One line in `COMMON` in `hooks/agent_brief.py` gives the same rule to every agent brief, reviewers included.

Mistake it stops: an agent met a refusal of a command, then sent the same command spelled with escapes or base64. The refusal had already said the act was not allowed, so the encoded form is the same act.

Outcome protected: a refusal stays final, so the owner or the orchestrator decides the next step.

False-alarm cost: an ordinary decode into a shell within ten minutes of an unrelated refusal in the same session is refused once, and the agent reports. An override lifts it. A guard.log deny from one agent brakes the orchestrator's own decode-and-run for ten minutes (accepted, the log names no agent). A decoded variable used as data in a shell's script, as `bash -c "./deploy.sh $PW"`, is refused too.

Not read:

- A decode written to a file and run later.
- A decode through `openssl`, `xxd` or a language runtime.
- An ANSI-C word inside the script of `eval` or `bash -c`.
- A glob spelling of a command word.
- A backtick pair after a backtick that never closes. Bash runs no part of that call.
- A PowerShell call.
- A decoded variable piped to a shell or to `source`: `s=$(base64 -d f); echo "$s" | sh`, `printf %s "$s" | bash`, `echo "$s" | source /dev/stdin`.
- A decode run in a container or remote shell: `docker exec c sh -c "$(base64 -d f)"`, `ssh host "$(base64 -d f)"`.
- A decode piped to `source /dev/stdin`, `. /dev/stdin` or `python3`, as `base64 -d f | source /dev/stdin`.

Kind: process
Home: hooks/guard_encoded.py
