# Operating model

Paste this into the project instructions. Replace each `<placeholder>`. The roster goes with it,
from `roster.md`.

## Standing roles

Each role is one long-running thread. A coordinator starts each role, and replaces it by the
hand-off rule below.

- **Triage.** The gatekeeper of the roadmap. Only triage writes a new step, merges two steps,
  changes the work order, or closes a step. Only triage publishes the roadmap page, from the head
  of the record branch. Triage reviews the whole roadmap at each batch merge and when the owner asks.
- **Build advisor.** Keeps about <4 to 6> build threads running, in roadmap order. Owns the build
  order, the merge queue and the integration branch. Dispatches no deferred step.
- **Local liaison.** Writes briefs for work that needs a local machine, and reads back the
  reports. May drive a Remote Control session on the owner's machine.
- **Merge hand.** Runs the merge command on an integration PR that the build advisor sends through
  the coordinator, on a machine that can run it. Prints the merge output on the terminal and never to a log only.

## Hand-off rule

Count each limit. Never wait for the owner to notice.

| Role | Messages | Second limit |
| --- | --- | --- |
| Triage | 40 | 25 placements |
| Build advisor | 40 | 12 build threads dispatched |
| Local liaison | 40 | 8 briefs written |

- Hand off at the first limit hit, at a phase change, or at once after a slip. A slip is a
  re-asked question, a reply that contradicts the roadmap, or a missed ruling.
- Each standing thread ends every reply with `tally: N messages, M <placements|dispatches|briefs>`.
- The coordinator reads the tally at each wake from a standing thread. It starts the successor
  when a limit is hit.
- On a hand-off, the old thread writes `handoffs/<role>-<date>.md` on the record branch from
  `role-handoff.md`. The coordinator starts the successor from that file, updates the roster,
  and resolves the old thread. The coordinator sends no broadcast. Threads read the roster.
- The owner may exempt a role from a limit. Write the exemption, with its date, in the roster.

## Autopilot

- Never wait on the owner. A step that needs the owner's answer gets a note line
  `Deferred (owner, <date>): <why>`, and waits. All other work runs, in roadmap order.
- A lane that hits a question for the owner parks that part, and goes on.
- A lane sends its green, reviewed head to the build advisor. A lane never rebases onto main and
  never merges.
- Each merge go names `frozen at <sha>`. Nobody pushes to that branch until the result is back.

## Filing

- A message can hold a ruling, a finding, a new step, a debt or a note. File it in the same turn,
  and tell the owner in one line where it went.
- Only triage writes new steps, merges, order and closes. Another thread sends the item to triage,
  with the owner's message attached.
- A thread rewrites the note, status and brief of a step it works on.
- The roadmap is a current record, not a log. Rewrite a note to what is true now. Keep each ruling
  as one dated line.
- A new or moved step near the top gets the line `Placed ahead of <step> (triage, <date>): <why>`.
- Pull right before each write.

## Messages between threads

- Send a message at once in two cases: work is blocked (a PR held, a lane stopped), or the owner
  asked for something to be passed on.
- Send non-urgent notes, findings and filing requests to the outbox: `roadmap/outbox/<thread-slug>.md`
  on the record branch. Each thread keeps one file and rewrites it to hold only what is unfiled.
- Triage reads the outbox at each wake, files each item, and removes what it filed.
- The session that owns a waiting item reads its answer. Nobody relays it. Skill `waiting-page`
  holds the protocol.
- A thread re-reads the roster right before it sends to a standing thread.

## Briefs

- A brief for a lane or a local session goes in `briefs/<step>-<slug>.md` on the record branch,
  from `brief.md`. Its full text also goes in the step's `ask` field.
- When a ruling changes a step, update the brief file and the `ask` copy in the same turn.

## Portability

Every process built here gets an explicit call: port it to the other repos, yes or no, and why.
The call is a judgment, never automatic, and never skipped.
