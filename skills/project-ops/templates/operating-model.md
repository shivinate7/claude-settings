# Operating model

Paste this into the project instructions. Replace each `<placeholder>`. The roster goes with it,
from `roster.md`.

## Session tiers

Every session that starts agents is an orchestrator. The tiers below are kinds of orchestrator.

- **Coordinator.** One per repo. It is the one session that starts other sessions. It starts
  triage and the batch runner together, as a trio, before any lane session. It holds lane state,
  writes each lane brief, starts each lane session in roadmap order, and talks with the owner. The load brake, not a
  number, decides how many lanes run at once. It does not rotate (see below).
  It tags itself and each session it starts `cs-repo:<owner>/<name>` and `cs-build:<tier>`
  (`coordinator`, `triage`, `batch-runner`, `arbiter` or `lane`), so another coordinator can find it.
- **Triage.** A standing session. The gatekeeper of the roadmap. Only triage writes a new step,
  merges two steps, changes the work order, or closes a step. Only triage writes the waiting page.
  At each publish, triage builds the roadmap block from the head of the record branch, with `--block`
  and `--live`. Triage, as the waiting-page writer, splices it into the repo's one page and
  publishes it (skill `roadmap`). Triage reviews the whole roadmap at each batch merge and when the owner
  asks. It may run agents.
- **Batch runner.** A standing session. It owns the integration batch, the CI waits, the merge
  tool runs and archiving finished lanes. It runs the merge tool on a machine that can run it.
  When the repo holds a standing merge grant (claude-settings record `standing-merge-grant`), it
  runs the merge tool on the coordinator's merge go, and asks the owner for no merge. Each merge it
  runs names `frozen at <sha>`. It prints the merge output on the terminal, never
  to a log only. It dispatches no deferred step.
- **Lane session.** Runs one lane as an orchestrator, with its own builder and reviewer agents.
  It reports up to the coordinator. Work that needs a local machine is a lane session whose brief
  names the machine. It may drive a Remote Control session on the owner's machine.

When the owner names the wrong tier, or brings work that belongs to another tier, the session
says so in one line: its own tier, the right tier, and why. It then handles the message or routes it.

A coordinator's work in another repo is compliance only, by hand-off or by its own lane PR there
(decision `session-tiers`, bullet "A coordinator in another repo"). Before it acts,
it checks whether that repo has an active coordinator: a live session tagged both
`cs-repo:<other owner>/<other name>` and `cs-build:coordinator`. It reads every page of
`list_sessions` and filters the tags itself. If one is active, it coordinates with it.
If none is active, it proceeds. It does not wait for a reply.

## Rotation of standing sessions

Count the use of triage and the batch runner. Never wait for the owner to notice.

The coordinator does not rotate. It writes its own handoffs and compacts in place. The coordinator
never hands its own sessions to a successor: a session may refuse a new coordinator as not its
parent, or miss a message while busy.

- At each wake, the coordinator reads triage's and the batch runner's tally from `get_session`:
  `external_metadata.context_usage` (`used_tokens` of `max_tokens`). A reading of 0, or none,
  is no reading: the coordinator asks that session for its tally instead. Without a project, each
  standing session ends every reply with its tally, and the owner reads it.
- The limits are `<triage limit>` and `<batch runner limit>`.
- Rotate a session at its limit, at a phase change, or at once after a slip. A slip is a
  re-asked question, a reply that contradicts the roadmap, or a missed ruling.
- On a rotation, in this order. The coordinator tells the session to rotate.
  1. The old session stops watching each page its role owns (the repo's one page, the project's
     waiting page). It notes the time, then answers each comment still open at that time on
     those pages.
  2. It drains its work in flight: it starts nothing new, and ends or hands over each wait it holds.
  3. It writes the hand-off file, `handoffs/<role>-<date>.md` on the record branch, from
     `role-handoff.md`, with that time. The file names each wait it handed over.
  4. The coordinator archives the old session, then the coordinator starts the successor from
     the hand-off file and updates the roster. The coordinator sends no broadcast. Sessions read
     the roster.
  5. The successor watches each page at once. It reads each page's comments since the time in
     the hand-off file.
- The owner may exempt a session from a limit. Write the exemption, with its date, in the roster.

## Autopilot

- Never wait on the owner. A step that needs the owner's answer gets a note line
  `Deferred (owner, <date>): <why>`, and waits. All other work runs, in roadmap order.
- A lane that hits a question for the owner parks that part, and goes on.
- A lane sends its green, reviewed head to the coordinator, which passes it to the batch runner.
  A lane never rebases onto main and never merges.
- Nobody pushes to a branch frozen for a merge go until the result is back. When the repo holds a
  standing merge grant, the coordinator gives each merge go under its grant, and the batch runner
  runs the merge tool on it. The owner is not asked.
- A session that waits on CI sets a timed check-in on each wait, and again after each red job.
- Stall check: at each wake, a standing session asks whether any lane, PR or batch moved since its last
  turn. When none moved and work is ready, it finds why and acts, or tells the owner what blocks it.
  It ends each turn that leaves work in flight with a timed check-in, so a lost wake costs one gap.

## Filing

- A message can hold a ruling, a finding, a new step, a debt or a note. File it in the same turn,
  and tell the owner in one line where it went.
- Only triage writes new steps, merges, order and closes. Another session sends the item to triage,
  with the owner's message attached.
- A session rewrites the note, status and brief of a step it works on.
- The roadmap is a current record, not a log. Rewrite a note to what is true now. Keep each ruling
  as one dated line.
- A new or moved step near the top gets the line `Placed ahead of <step> (triage, <date>): <why>`.
- Pull right before each write.

## Messages between sessions

- Send a message at once in two cases: work is blocked (a PR held, a lane stopped), or the owner
  asked for something to be passed on.
- Send non-urgent notes, findings and filing requests to the outbox: `roadmap/outbox/<session-slug>.md`
  on the record branch. Each session keeps one file and rewrites it to hold only what is unfiled.
- Triage reads the outbox at each wake, files each item, and removes what it filed.
- The session that owns a waiting item reads its answer. Nobody relays it. Skill `waiting-page`
  holds the protocol.
- A session re-reads the roster right before it sends to a standing session.

## Briefs

- A brief for a lane or a local session goes in `briefs/<step>-<slug>.md` on the record branch,
  from `brief.md`. Its full text also goes in the step's `ask` field.
- When a ruling changes a step, update the brief file and the `ask` copy in the same turn.

## Portability

Every process built here gets an explicit call: port it to the other repos, yes or no, and why.
The call is a judgment, never automatic, and never skipped.
