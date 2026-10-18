# session-board keeps small records, and /safe-stop queues one prompt

## The ruling

The session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) gives one view of all
sessions and a safe stopping point, with no typing of "status?" into each one.

Each session with the mod writes two small records to `$.store`: `sess:<sessionId>`, under 1 KB, and
`detail:<sessionId>`, under 3 KB. They hold names and counts. These are the repo folder name, branch,
state, git counts with their read time, and agent and spawn counts. They also hold the last 5 tool calls
and the receipt for the last turn. A session with no entry shows "no detail".

Update-ready holds only when all five conditions hold. They are the owner's definition:

- No running agents.
- State is "waiting".
- No permission ask.
- No unpushed commits.
- A clean tree.

Running servers and background tasks are not part of update-ready.

Unknown is never ready. Git counts are unknown when the reading is older than 60 s or stamped more than
30 s ahead. They are also unknown when the git call failed or was slow, and when the branch has no
upstream.

Timing:

- Each session writes its entry on a 30 s heartbeat. The board hides an entry older than 2 minutes, and
  one stamped more than 30 s ahead of now.
- Git runs from an argv array, with no shell, `core.fsmonitor=false`, `--no-optional-locks`, and a 5 s
  cap. One read runs at a time. A slow read doubles the idle wait, up to 300 s.
- The one-day sweep deletes records a day past their last beat. It skips a session that `claude agents`
  lists as live. It deletes only when that list is a valid JSON array; a valid empty list counts as real.
  An unreadable check is not a death (`verification-report-unknown-reads`).

Privacy:

- The mod stores no prompt text, no file content, and no folder path. The files-touched figure is a count.
- The recent list holds the tool name. It adds a file name only for Read, Edit, Write, MultiEdit,
  NotebookEdit, Glob and Grep. A Bash command and an MCP tool give the tool name only.
- A name that looks secret shows as "(secret file)". The rule copies the plain-diff secret filter
  (`plain-diff-mod-limits`).
- The mod shows no cost figure. The figure from `$.session.usage()` was unreliable.

Stop:

- `/safe-stop` refuses non-user origins by a block-list in `hooks/lib.mjs`. Other origins run, including
  `unclassified`.
- It asks the installed handoff hook for its path functions, through `python3` or `python`, with `-I -B`
  and the config folder as cwd. A run makes the handoff folder. A plan makes none.
- It sends this session one prompt with `$.prompt.submit`. The prompt tells the session to finish or park
  its step and to start no new work or agent. It tells the session to follow the hook's prompt file,
  rewrite the handoff whole, and reply with one line: branch, uncommitted files, unpushed commits and
  running agents. The session writes the handoff. The mod writes none.
- The reply says the prompt is queued until the session is idle. If the host drops the prompt, the reply
  says "could not send".
- A path over 4000 characters is refused, not cut.
- `/safe-stop plan` prints the prompt and sends nothing.

Safety of the session:

- Every host call sits in a try. A failure logs one line to the debug log, prefixed "session-board:".
- Each hook waits at most 100 ms for its work. The work finishes on its own.
- An ask clears when its tool call returns. A git read that began before a turn start is dropped.
- Session end deletes both records, for any reason.

Reason: each record is small. It holds names and counts, no prompt and no file content.

Kind: process
Home: mods/session-board/hooks/lib.mjs
