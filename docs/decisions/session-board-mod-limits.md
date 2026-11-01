# session-board keeps small records

## The ruling

The session-board mod (`mods/session-board`, commands `/board` and `/safe-stop`) gives one view of all
sessions and a safe stopping point, with no typing of "status?" into each one. Reason: each record is
small. It holds names and counts, no prompt and no file content. `/safe-stop` is in
`safe-stop-queues-one-prompt`.

Update-ready holds only when all five conditions hold (the owner's definition):

- No running agents.
- State is "waiting".
- No permission ask.
- No unpushed commits.
- A clean tree.

Running servers and background tasks are not part of update-ready. Unknown is never ready. Git counts are
unknown when the reading is stale or stamped ahead, when the git call failed or was slow, and when the
branch has no upstream.

Each session writes a small summary record and a small detail record to `$.store`, on a heartbeat. An idle
session reads git at a turn end, on attach, and then about every 5 minutes. A git reading counts for 330
seconds (`READ_MAX_AGE_MS`), so an idle board stays update-ready and does not show unknown. The
board hides a stale entry. The one-day sweep deletes old records and skips a session that `claude agents`
lists as live. It deletes only when that list is a valid JSON array; a valid empty list counts as real.
An unreadable check is not a death (`verification-report-unknown-reads`). Session end deletes both
records, for any reason.

Privacy:

- The mod stores no prompt text, no file content, and no folder path. The files-touched figure is a count.
- The recent list holds the tool name, plus a file name for file tools only. A Bash command and an MCP
  tool give the tool name only.
- A name that looks secret shows as "(secret file)". The rule copies the plain-diff secret filter
  (`plain-diff-mod-limits`).
- The mod shows no cost figure. The figure from `$.session.usage()` was unreliable.

Safety of the session: every host call sits in a try and a failure logs one line prefixed
"session-board:". Git reads run with no shell and no optional locks. Each hook waits a bounded time for
its work. An ask clears when its tool call returns. A git read that began before a turn start is dropped.

## The question-box check

session-board holds one guard: rule `question-box-while-work` refuses AskUserQuestion while this session's own work runs, or once it has started another session (`questions-go-to-owner`, questions go to the owner). Every other hook in the mod observes only.

- **Agents.** The host's agent list, read once per box. A pending, running or waiting agent counts. The asking loop does not count itself.
- **Background tasks.** A background command or workflow counts. A Bash call whose result names a background task adds it, and a Workflow call adds its task. Its task notice removes it. A TaskStop call removes its task too (see "A missed notice" below). A missed notice holds the box until Claude runs TaskStop on that id or the session ends. A monitor does not count: it watches for as long as the session lives.
- **Started sessions.** A tool call that starts a session and answers without error counts: the desktop start (`mcp__ccd_session__start_session`, the guard's `SESSION_TOOL`) or the cloud start (`mcp__claude-code-remote__create_session`). Exact names only; a deny or an error result is no start. A start made inside an agent counts too. Once the count is above zero, every box is refused for the rest of the session, with no agent read: a started session may wait on this one. The count lives in the start record `started:<id>`, which `session.end` leaves. A mod reload, or a restart or resume under the same id, reads it back once. A `/clear` carries the count to the new id; an in-process resume starts at the resumed session's own count. Each start writes the record once, and a `/clear` that carries a count writes it once more. The sweep takes a start record with its board entry. With no board entry left, it takes one a day past its last write, unless its session is live or is this one. A new session in the same process starts at its own count.
- **The refusal** counts what runs and the sessions started. It says to ask in the reply instead. If the owner has not answered in 5 minutes, the question goes to the waiting page's writer. Then keep working on what does not depend on the answer (`questions-go-to-owner`, questions go to the owner).
- **Unknown.** An agent list that throws or takes over 3 s lets the box through. The debug log and `guard.log` each get one line that says unknown.
- **Not covered.** An agent that starts in the same response as the box, if the box is checked first. A background task that started before the mod last loaded, or that another tool started, until its notice or a TaskStop. A Routine (`create_trigger`, `fire_trigger`): its sessions do not wait on the caller. A restart under a new id. A session stopped over a day may lose its count at the next sweep, and a resume then reopens the box.

Why: Oct 26, a UI session waited on a question box while its background agents filled the disk and crashed it. Oct 27, an orchestrator with no agent or command of its own opened the box, and the lane sessions it had started waited on it.

Risk kind: incident, per `building-guard-needs-incident`. Landed 2026-10-27.

Cost, per `outcomes-mechanize-rules`: process starts, none on a box allowed after a good read, and none for a session start; one python start per `guard.log` line (a refusal, or a box allowed because the list was unknown). Files written: that one line. How often: once per AskUserQuestion call. No timer and no watcher; the agent list is read inside the check. `mods/session-board/session-board.test.mjs` (the "question box" cases) pins the zero starts on an allowed box and one line per refusal.

## A missed notice

Owner ruling, waiting-page item 117, 2026-11-01 11:53 CST (picks a and b):

- (a) The mod has no `classic.Stop` handler. It once reset the tracked set from the Stop input's `background_tasks` at each main-loop turn end. The built-in plugin sec-default sends every `classic.*` event past user mods, so that handler never ran. The same reroute is in `decision-watch-mod-limits` (the decision-watch mod's record, section "The event is turn.complete"). The mod still listens on `turn.complete` and others; only `classic.*` is lost.
- (b) A tracked task clears when a TaskStop call answers without error. The id comes from the output `task_id`, else the input `task_id`, else the input `shell_id`, else the output message "Successfully stopped task: <id>" (the text `hooks/stall_watch.py` reads). An `isError` or `is_error` result is no answer.
- A TaskStop on a task that already ended fails with "No task found with ID: <id>" (measured by the coordinator, 2026-11-01 12:10 CST). That failure also clears the id, thrown or as an error result, because no task has it. Any other failure keeps the task.

Evidence for (a), all read outside this repo: the sec-default README, "Where it is seated" (marketplace copy `mods/sec-default/`); the installed binary string `classic.*",(n,r,o)=>o.to(r,"append")`; and in a cloud session the host's own notice "session-board: its classic.Stop hook was skipped". The limit holds on every surface where the CLI seats sec-default (Team or Enterprise orgs). On the owner's desktop and terminal it is unmeasured.

What protects the gap now: a task's notice, or a TaskStop on that id (an ended task too). A missed notice holds the box until one of those runs or the session ends. A box refused for a stale task is a false alarm; the refusal names the task count.

Protected by `mods/session-board/session-board.test.mjs`: "register: adds no classic.* hook", and the TaskStop cases (output `task_id`, `shell_id`, message id, `is_error`, "No task found" thrown and as a result, any other failure keeps the task).

Cost: no process start, no file, no timer. The clear runs inside the `tool.call` handler already running.

Kind: process
Home: mods/session-board/hooks/lib.mjs
