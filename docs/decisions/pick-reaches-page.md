# A coordinator's pick reaches the owner's page

## The ruling

Owner, 2026-11-12 12:09 CST: "this needs to be mechanized". A coordinator that takes a pick the owner could overrule sends it to the page writer, so it shows on the waiting page as a `stands` item (skill `waiting-page`, "Add an item"). The writer is triage.

The guard rule `pick-reaches-page` refuses a send_message from a coordinator. The message has a line that opens `Coordinator pick`, after markdown lead characters, in any case, outside a fenced block. The send goes to a session that is not the page writer.

The send passes when a send to the writer since the last human message names the same pick. The key is the rest of the line, casefolded, with its markdown and full stop cut. The owner's typed override lifts the rule (`owner-override`).

## The mistake

On 2026-11-12 a coordinator took 19 undoable picks (rule `parallelism-keep-going`, take a pick that can be undone). It sent each only to lanes. None reached the waiting page.

## The harm

The owner could not see or overrule 19 picks. A pick that stands is only safe while the owner can see it and change it (decision `questions-go-to-owner`, "Take a pick that can be undone").

## The guard

- Only a coordinator's send is judged: the session's own record, read from the transcript, holds the tag `cs-build:coordinator`. A lane's send passes.
- The remedy names the page writer and the waiting-page skill. It does not name the lane as a way round.
- Cost: a message with no marker reads no transcript. A marker message from a session with an own id costs one own-record read and one transcript read. No file, no process, no timer (rule `outcomes-mechanize-rules`).
- The scanner reads line by line with one fence flag, so a lone quote, backtick or comment opener in prose hides no marker (rule `building-scanner-respects-strings`).

Gaps, each failing open:

- An unreadable transcript, or no transcript path, passes the send.
- A stale own record passes: a `set_session_tags` call after the record is not checked. A coordinator tagged after its record was read is judged by the old tags.
- No page writer known, from neither a `meta/page` read nor the layout's `page-writer` key, passes the send. The coordinator then has no one to send the pick to.
- An undelivered send to the writer counts as a send. Only the call is read, not its result.
- A message with two markers needs each key named by a send to the writer. A writer send that holds both lines covers both. The reason names the first key not covered.
- A pick written in another form, such as `- Coordinator pick` (a bullet), `Pick:` or a pick inside prose, is not read. A pick in a tool other than send_message is not read.

Kind: process
Home: rule:questions-go-to-owner
Home: hooks/guard_merge.py
