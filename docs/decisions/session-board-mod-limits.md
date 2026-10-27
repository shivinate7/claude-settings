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

session-board holds one guard: rule `question-box-while-work` refuses AskUserQuestion while this session's own work runs (`questions-go-to-owner`, questions go to the owner). Every other hook in the mod observes only.

- **Agents.** The host's agent list, read once per box. A pending, running or waiting agent counts. The asking loop does not count itself.
- **Background commands.** A Bash call whose result names a background task adds it. Its task notice removes it. At each main-loop turn end, the engine's own list of work in flight (the Stop input's `background_tasks`) replaces the set, so a missed notice lasts one turn at most.
- **The refusal** counts what runs and says to ask in the reply and on the waiting page, then keep working.
- **Unknown.** An agent list that throws or takes over 3 s lets the box through. The debug log and `guard.log` each get one line that says unknown.
- **Not covered.** An agent that starts in the same response as the box, if the box is checked first. A workflow's agents, which the host's list leaves out. A background command that started before the mod last loaded, until the next turn end.

Why: Oct 26, a UI session waited on a question box while its background agents filled the disk and crashed it.

Risk kind: incident, per `building-guard-needs-incident`. Landed 2026-10-27.

Cost, per `outcomes-mechanize-rules`: process starts, none on an allowed box; one python start per `guard.log` line (a refusal or an unknown). Files written: that one line. How often: once per AskUserQuestion call. No timer and no watcher; the agent list is read inside the check. `mods/session-board/session-board.test.mjs` (the "question box" cases) pins the zero starts on an allowed box and one line per refusal.

Kind: process
Home: mods/session-board/hooks/lib.mjs
