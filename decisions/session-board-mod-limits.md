# session-board keeps small records, and /safe-stop queues one prompt

## The ruling

The session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) gives one view of all
sessions and a safe stopping point, with no typing of "status?" into each one.

Each session with the mod writes two records to `$.store`:

- `sess:<sessionId>` is under 1 KB. It holds the repo folder name, the branch, the state, and the git
  counts with their read time. It also holds the running agent count, spawn counts by agent type, the
  context percent, and a time stamp.
- `detail:<sessionId>` is under 3 KB. It holds the last 5 tool calls, a count of files touched, agent
  status, spawn counts, permission check counts, and the receipt for the last turn.

The board seeds its rows from `claude agents --json`. It merges store entries into those rows by session
id. A session with no entry shows "no detail".

Update-ready holds only when all five conditions hold:

- No running agents.
- State is "waiting".
- No permission ask.
- No unpushed commits.
- A clean tree.

Unknown is never ready. Git counts are unknown in four cases:

- The reading is older than 60 s.
- The reading is stamped more than 30 s ahead.
- The git call failed or was slow.
- The branch has no upstream.

Timing:

- Each session writes its entry on a 30 s heartbeat.
- The board hides an entry older than 2 minutes, and one stamped more than 30 s ahead of now.
- The board reads the 200 newest entries and shows 40 rows.
- Git runs from an argv array, with no shell, `core.fsmonitor=false`, `--no-optional-locks`, and a 5 s
  cap. It runs at turn end and on the idle heartbeat. One read runs at a time.
- A read that takes 5 s or more doubles the idle wait, up to 300 s. A quick read resets it to 30 s.
- The one-day sweep deletes records a day past their last beat. It skips a session that `claude agents`
  lists as live. It deletes records only when that list is a valid JSON array. A valid empty list counts
  as real. An unreadable check is not a death (`liveness-read-is-platform-specific-and-unreadable-is-not-death`).

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
- It asks the installed handoff hook for its path functions, through `python3` or `python`. The call uses
  `-I -B` and the config folder as cwd. A run makes the handoff folder. A plan makes none.
- It sends this session one prompt with `$.prompt.submit`. The prompt tells the session to finish or park
  its step, and to start no new work or agent. It also tells the session to follow the hook's prompt file
  and rewrite the handoff whole, and to reply with one line: branch, uncommitted files, unpushed commits
  and running agents. The session writes the handoff. The mod writes none.
- The reply says the prompt is queued until the session is idle. If the host drops the prompt, the reply
  says "could not send".
- A path over 4000 characters is refused, not cut.
- `/safe-stop plan` prints the prompt and sends nothing.

Safety of the session:

- Every host call sits in a try. A failure logs one line to the debug log, prefixed "session-board:".
  Some handlers stay silent.
- Five points wait at most 100 ms for their work: session start, turn start, turn end, a permission ask,
  and the end of a tool call. The work finishes on its own.
- An ask clears when its tool call returns. A git read that began before a turn start is dropped.
- Session end deletes both records, for any reason.

Reason: each record is small. It holds names and counts, no prompt and no file content.

Kind: build
Plan: decisions/session-board-mod-limits.md#the-ruling (all)
Home: mods/session-board/hooks/lib.mjs

## Named limits

- Running servers and background tasks are not part of update-ready. The five conditions are the owner's definition.
- The per-turn cost of the git read is unmeasured. So is the cost of `claude agents --json` on a very large session list.
- The cases use a fake host, not the desktop app.

## Holes, named

Debts: `sb-pane-untested`, `sb-prompt-turn-end`, `sb-hook-order-unproven`, `sb-auto-approve-unseen`,
`sb-host-calls-unbounded`, `sb-ghost-row-race`, `sb-safe-stop-origin`, `sb-config-folder-guess`,
`sb-backoff-cap`, `sb-glob-path-names`, `sb-agents-json-cost`, `sb-filter-driver-runs`,
`sb-store-not-shared`, `sb-process-desktop-unknown`, `sb-command-turn-unknown`,
`plain-diff-secret-file-names`.
