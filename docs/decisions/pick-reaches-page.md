# A coordinator's pick reaches the owner's page

## The ruling

Owner, 2026-11-12 12:09 CST: "this needs to be mechanized". A coordinator that takes a pick the owner could overrule makes it show on the waiting page (skill `waiting-page`, "Add an item"). It sends the pick to the page writer.

The guard rule `pick-reaches-page` refuses a send_message from a coordinator. A line of the message opens `Coordinator pick` or `Coordinator picks`, after markdown lead characters and an optional list lead (`-`, `+`, `1.`, `1)`), in any case. The marker ends with `:`, `.`, `,`, `;`, a dash and a space, or the line's end. So `Coordinator pick summary:` is no marker. The line is outside a closed fenced block. The send goes to a session that is not the page writer.

The send passes when the pick is named since the last human message. A send to the writer names it when its message has the same pick line. The key is the rest of the line, casefolded, with its markdown and full stop cut. When this session is itself the page writer, it cannot send to itself. Its own set, update or batch to the items collection since the last human message names the pick when the written text has the same pick line. With no human message in the transcript, the whole transcript is the turn. The owner's typed override lifts the rule (`owner-override`).

## The mistake

On 2026-11-12 a coordinator took 19 undoable picks (rule `parallelism-keep-going`, take a pick that can be undone). It sent each only to lanes. None reached the waiting page.

## The harm

The owner could not see or overrule 19 picks. A pick that stands is only safe while the owner can see it and change it (decision `questions-go-to-owner`, "Take a pick that can be undone").

## The guard

- Only a coordinator's send is judged: the session's own record, read from the transcript, holds the tag `cs-build:coordinator`. A lane's send passes.
- The remedy names the page writer and the waiting-page skill. It does not name the lane as a way round.
- Cost: a message with no marker reads no transcript. A marker message from a session with an own id costs one own-record read and one transcript read (not pinned: the spy case counts file opens, 0 with no marker and 2 with one). When the transcript names no writer, it adds the layout's extras-file read. No file written, no process, no timer (rule `outcomes-mechanize-rules`).
- The scanner reads line by line, so a lone quote, backtick or comment opener in prose hides no marker (rule `building-scanner-respects-strings`). A fence with no closing line hides nothing, and a one-line span such as "```a``` note" opens no fence.

Gaps:

- An undelivered send to the writer counts as a send. Only the call is read, not its result.
- Every unreadable record fails open: an unreadable transcript, no transcript path, no own session id, no own record, or no page writer known passes the send. A stale own record passes too: a `set_session_tags` call after the record is not checked.
- Fail-open costs the owner a visible pick, not a lost one. How often it happens is unmeasured.
- A message with two markers needs each key named. A writer send that holds both lines covers both. The reason names the first key not covered.
- A pick in a tool other than send_message, or written as prose or as `Pick:`, is not read.

Kind: process
Home: rule:questions-go-to-owner
Home: hooks/guard_merge.py
