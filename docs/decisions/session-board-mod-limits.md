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

Kind: process
Home: mods/session-board/hooks/lib.mjs
