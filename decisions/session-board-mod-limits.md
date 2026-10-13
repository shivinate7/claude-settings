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

Each hole ships under the three-round review cap.

- The pane draw is untested in the desktop app. Example: a press on a row does not open its detail view. Why it ships: only the app or a terminal draws the pane.
- The permission signal is a tool check that returns "ask". Turn end during a prompt is unknown. Example: a turn ends while a prompt is still open. Why it ships: headless mode cannot test it.
- The host hook order is untested. The mod assumes that the host runs the permission check inside `next()`. Example: a permission label outlasts its tool call. Why it ships: a headless run did not confirm the order.
- An auto-approve mode can answer an "ask" with no person present. The mod cannot tell this apart. Example: a "permission" label shows during a call that no person answers. Why it ships: the mod has no mode check.
- Running servers and background tasks are not part of update-ready. Example: a session with a dev server reads "ready". Why it ships: the five conditions are the owner's definition.
- The 100 ms wait does not bound every host call. At session start, `$.session.repo()` and `$.command.register()` are awaited with no bound. At session end, the store deletes are unbounded. On clear or resume, `$.session.repo()` is unbounded too. Example: a slow store delete holds the session end. Why it ships: unmeasured.
- The clear or resume race can leave a ghost row. The end hook deletes the records before it marks the old id as retired. A beat that writes in that gap leaves the old entry. Example: a beat fires between the deletes and the mark. Why it ships: the gap is narrow, and the 2-minute rule hides the row. A held write that lands later is removed when it lands.
- The origin check is a block-list. An unclassified origin still runs `/safe-stop`. Example: a command from "unclassified". Why it ships: the desktop app can send "unclassified". The check does not prove that a person typed the command.
- The config folder is a guess. A drive-letter USERPROFILE means Windows. Under Git Bash, HOME may be `/c/Users/x`, which a Windows program cannot use. That form is avoided only when USERPROFILE holds a drive letter. Other MSYS forms are not handled. Example: no USERPROFILE, and HOME is `/c/Users/x`. Why it ships: `CLAUDE_CONFIG_DIR` overrides it.
- A quick git read resets the back-off. A repo whose read takes over 5 s stays unknown. Example: a status read of 6 s. Reads then run up to 5 minutes apart, and the row reads unknown. Why it ships: a larger cap is unmeasured.
- Grep and Glob paths that look like a file name show by name. Example: a folder named `v1.2`. Why it ships: the file system check is not built.
- `claude agents --json` runs on each board refresh. Example: a very large session list. Why it ships: its cost is unmeasured.
- A filter driver named in repo git config can run during `git status`. The mod sets `core.fsmonitor=false`, but it does not disable filter drivers. Example: a clean filter with a matching `.gitattributes` entry. Why it ships: the driver needs repo config that the user already trusts.
- The cost figure from `$.session.usage()` is shown nowhere. Why it ships: the figure was unreliable.
- The store is per plugin and per config folder. Sessions loaded another way, or under another config folder, do not show. Example: a `--plugin-dir` run writes `session-board_inline-<hash>.json`. Why it ships: the host names the file. Whether the app and the terminal share one store is unknown.
- The API notes `$.process` as CLI only. If it fails in the desktop app, no session reads ready, and the `claude agents` seed is missing. Example: the board shows store entries alone. Why it ships: the desktop app is untested.
- It is unknown whether a prompt sent from a command starts a turn in the app. Example: `/safe-stop` reports "queued", and no turn starts. Why it ships: untested in the app.
- The secret name rule misses some names. Example: `terraform.tfstate` shows by name. The same gap is in `plain-diff-mod-limits` (the plain-diff secret filter). Why it ships: the name list holds only the names known so far.
