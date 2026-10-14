# session-board keeps small records, and /safe-stop queues one prompt

## The question

What does the session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) store and show? What stops it from leaking or breaking a session? Which limits stay open?

## The ruling

Owner intent: stop typing "status?" into many sessions. See all sessions at once. Find a safe stopping point.

Each session with the mod writes two records to `$.store`:

- `sess:<sessionId>` is under 1 KB. It holds the repo folder name, the branch, and the state. It also holds the git counts and their read time. It also holds the running agent count, spawn counts by agent type, the context percent, and a time stamp.
- `detail:<sessionId>` is under 3 KB. It holds the last 5 tool calls, a count of files touched, and agent status. It also holds spawn counts, permission check counts, and the receipt for the last turn.

The board seeds its rows from `claude agents --json`. It merges store entries into those rows by session id. A session with no entry shows "no detail".

Update-ready holds only when all five conditions hold:

- No running agents.
- State is "waiting".
- No permission ask.
- No unpushed commits.
- A clean tree.

Unknown is never ready. Git counts are unknown in four cases. The reading is older than 60 s, or stamped more than 30 s ahead. The git call failed or was slow. The branch has no upstream.

Timing:

- Each session writes its entry on a 30 s heartbeat.
- The board hides an entry older than 2 minutes. It also hides an entry stamped more than 30 s ahead of now.
- The board reads the 200 newest entries and shows 40 rows.
- Git runs from an argv array, with no shell, `core.fsmonitor=false`, `--no-optional-locks`, and a 5 s cap. It runs at turn end and on the idle heartbeat. One read runs at a time.
- A read that takes 5 s or more doubles the idle wait, up to 300 s. A quick read resets it to 30 s.
- The one-day sweep deletes records a day past their last beat. It skips a session that `claude agents` lists as live. It deletes records only when that list is a valid JSON array. A valid empty list counts as real.
- Same principle as `liveness-read-is-platform-specific-and-unreadable-is-not-death`: an unreadable check is not a death.

Privacy:

- The mod stores no prompt text, no file content, and no folder path.
- The files-touched figure is a count.
- The recent list holds the tool name. It adds a file name only for Read, Edit, Write, MultiEdit, NotebookEdit, Glob and Grep.
- A Bash command and an MCP tool give the tool name only.
- A name that looks secret shows as "(secret file)". The rule copies the plain-diff secret filter, cited as `plain-diff-mod-limits`.
- The mod shows no cost figure.

Stop:

- `/safe-stop` refuses non-user origins by a block-list in `hooks/lib.mjs`. Other origins run, including `unclassified`.
- It asks the installed handoff hook for its path functions, through `python3` or `python`.
- The call uses `-I -B` and the config folder as cwd. A run makes the handoff folder. A plan makes none.
- It sends this session one prompt with `$.prompt.submit`. The prompt tells the session to finish or park its step, and to start no new work or agent.
- The prompt also tells the session to follow the hook's prompt file and rewrite the handoff whole. It asks for one reply line: branch, uncommitted files, unpushed commits, and running agents.
- The session writes the handoff. The mod writes none.
- The reply says the prompt is queued until the session is idle. If the host drops the prompt, the reply says "could not send".
- A path over 4000 characters is refused, not cut.
- `/safe-stop plan` prints the prompt and sends nothing.

Safety of the session:

- Every host call sits in a try. A failure logs one line to the debug log, prefixed "session-board:". Some handlers stay silent.
- Five points wait at most 100 ms for their work.
- They are session start, turn start, turn end, a permission ask, and the end of a tool call. The work finishes on its own.
- Session end deletes both records, for any reason.

## Why

The owner needs one view of all sessions and a safe stop, without typing into each one. Each record is small. It holds names and counts. It holds no prompt and no file content.

## What it costs

- One git read per turn end and per idle beat, each up to 5 s. One run in the largest repo took 0.11 s with a warm cache, on one machine. The per-turn cost is unmeasured.
- One `claude agents --json` call per board refresh. Its cost on a very large session list is unmeasured.
- One entry write per session every 30 s.

## What protects it

- `mods/session-board/session-board.test.mjs`: 119 cases. On head 50e55bd, 119 pass and 0 fail. The cases use a fake host, not the desktop app. Red runs are recorded at fdfdba0, 5581a3b, 3cdebf7 and b25e55d.

## Review rounds

Three review rounds. The fix commits are 23b7ee7, a7a0e00 and 50e55bd. Blockers found and fixed:

- `/safe-stop` ran python in the repo folder without `-I`. A repo file `json.py` would run. Now the call uses `-I`. The cwd is the config folder.
- Secret file names were stored in the detail record. Now they show as "(secret file)".
- A stale ask label. Now an ask clears when its tool call returns.
- A git read kept a stale "ready". Now a failed or old reading is unknown. A read that began before a turn start is dropped.
- The sweep deleted live records when the agent list was unusable. Now it deletes nothing unless the list is a valid JSON array.

## Holes, named

Debts: `sb-pane-untested` (pane draw), `sb-prompt-turn-end` (turn end in a prompt), `sb-hook-order-unproven` (hook order), `sb-auto-approve-unseen` (auto-approve). `sb-host-calls-unbounded` (host calls), `sb-ghost-row-race` (clear or resume), `sb-safe-stop-origin` (origin check), `sb-config-folder-guess` (config folder). `sb-backoff-cap` (back-off cap), `sb-glob-path-names` (folder names), `sb-agents-json-cost` (agents cost), `sb-filter-driver-runs` (filter drivers). `sb-store-not-shared` (store sharing), `sb-process-desktop-unknown` (process call), `sb-command-turn-unknown` (command turn), `plain-diff-secret-file-names` (secret names).

## Named limits

- Running servers and background tasks are not part of update-ready. The five conditions are the owner's definition.
- The cost figure from `$.session.usage()` is shown nowhere. The figure was unreliable.

Kind: process
Home: mods/session-board
