# Operating model

Paste this into the project instructions. Replace each `<placeholder>`. The roster is not pasted: it lives on the record branch
(`roster.md` is its form; ruling R22).

## Session tiers

A spawner is a session that starts its own agents. Each session role is a set of jobs, worn as a hat.

- **Coordinator.** One per repo. It is the one session that starts other sessions. It starts
  triage and the batch runner together, as a trio, before any lane. It holds lane state
  and writes each lane brief. It starts each lane in roadmap order, with `model` (the lane row's),
  `source_url` (the repo), effort `medium` and `title` `Lane <branch slug>: <task>`. It sets the tags `cs-repo`, `cs-build:lane`, `cs-step`
  and `cs-topic`. Its whole brief is the first prompt, and it opens with the Grant line. It talks with the owner. Before a fix lane for a red CI case, it runs
  `~/.claude/bin/merge --touches --run <run id>` and reads each open PR named (decision `session-tiers`, "Who starts which session"). On a local session, the load
  brake, not a number, decides how many lanes run at once. It does not rotate (see below).
  It archives each other finished session it started at its next wake, once it has read the report (ruling R46). It sends each lane that triage flags one line: reply if you are stuck and nobody picked it up (ruling R56 point 3).
  The arbiter is a separate role that holds a repo's ruling and grant voice (decision `session-tiers`, Arbiter).
  It tags itself and each session it starts `cs-repo:<owner>/<name>` and `cs-build:<tier>`
  (`coordinator`, `triage`, `batch-runner`, `arbiter` or `lane`), so another coordinator can find it.
  A lane also gets `cs-topic:<topic slug>`, its one topic, and a `cs-step:<step id>` for each step it takes, so triage can see each step is live.
- **Triage.** A standing session. It writes the roadmap. Only triage writes a new step,
  merges two steps, changes the work order, or closes a step. Triage always writes the waiting page; in a run with one lane the lane wears triage's hat and writes it.
  At triage start, when the repo has no waiting page, triage makes it, with no separate grant (skill
  `waiting-page`, "Make a repo's page").
  At each publish, triage builds the roadmap block from the head of the record branch, with `--block`
  and `--live`. The `--live` file carries a `sessions` key: each `list_sessions` row (every page) with
  `id`, `session_status` and `tags`. The roadmap build script reads it to list steps in progress with no live lane.
  Each pull row carries `createdAt`, so the roadmap build script can list a stale draft. It also carries `held` (true when
  the batch runner's hand-in or hold list names the pull) and `reviewLog` (true when the pull has a posted review log),
  JSON bools, omitted when false or unknown. Each item row carries
  `lane` when the page item has one, so it can list an item whose lane is gone.
  The file also carries `landedPulls`: each pull request closed in the last 14 days whose base is the default
  branch, with `number`, `branch`, `head` and `merged`. The build marks a step landed from it when no `Step:` trailer is on main.
  At each publish, triage also disposes each `stalled step:` line the build prints (the build exits 1 on one): a
  step with no live lane and no open PR becomes `todo` or `done`, or gets a `paused` field with who decides; an item
  is re-routed or closed. When triage marks a step `done`, its note gets the line
  `Done check green on main: <PR or commit>`, naming where the done check went green. The ref is `#N`, `PR N`,
  a pull or commit URL, or a commit hash. With no such proof, the step stays open, not `done`.
  Triage does not end its wake while such a line prints: the Stop hook (`lint/report_guard.py`)
  refuses to end a turn while the newest build output in the transcript has one. A second Stop is released only when
  the report's Input Needed section names every stalled step id and item number, which escalates it to the coordinator.
  Triage, as the page writer, splices it into the repo's one page and
  publishes it (skill `roadmap`). Triage reviews the whole roadmap at each batch merge and when the owner
  asks. At each review, triage reads standing sessions' `Recovered:` lines, counts their `Handoff gave:` lines, and brings the no-limit
  rotation ruling (claude-settings decision `session-tiers`) back to the owner if losses repeat.
  Triage also writes the roster on the record branch (ruling R22, a respawn rewrites every session id at once)
  and the rulings store, one file per owner ruling, from the owner's quoted words with their time (ruling R59,
  a ruling governs at once; `lint/ruled_store.py` checks the store). It sends the coordinator the ready list.
  It closes the build's stale drafts once, then at each batch (decision `stalled-steps`; step
  `stale-draft-joint-pass`). It keeps the list of the sessions the coordinator starts.
  It flags to the coordinator each lane whose step another step waits on, or that is on the express list (R55).
  It flags it only when the lane has sent no report or message since the last read (rulings R54 and R56 points 1 and 2). It writes each Opus grant on the step. It may run agents.
- **Batch runner.** A standing session. It owns the integration batch until the cutover (claude-settings decision `all-repos-switch-together`); after it, it merges each lane PR alone, on its own green run. It also owns the CI waits, the merge
  tool runs and archiving lanes. It runs the merge tool on a machine that can run it. After each merge it archives each lane that `merge --idle-lanes --live <file>` prints, for the coordinator (decision `session-tiers`, Archiving scope; ruling R46). The coordinator archives each other finished session it started.
  In each wake it runs `merge --reviewed` once, with one `--root` per repo it owns (its `cs-repo:` tags), and
  opens or builds each batch the output names in that wake. It runs each `--confirm` in the foreground (see below). A foreground wait on one repo's CI held another repo's
  hand-offs for 1 h 16 min once (decision `session-tiers`, incident 2026-11-07). Batch steps are in skill `ci-hygiene`, step 8. The left-out list
  and `--confirm --express` are in the merge tool's usage.
  It runs `merge <pr> --confirm --head <sha>` on the integration PR while it is a draft, with the head
  its CI ran on. That step rebuilds the
  records page and pushes it. When the draft run of the pushed head shows, the batch runner marks
  the PR ready, so the branch is final at ready (claude-settings
  record `records-index-at-merge`). Then it runs `--confirm --head <sha>` again to merge, with the head
  the ready run ran on. Until the cutover, batches overlap
  (claude-settings record `no-merge-during-batch-ci`: no merge while a batch's CI runs). Once
  batch N's ready run starts, the batch runner builds batch N+1 on N's head at ready, as a PR on
  the same base, and runs it. N may merge while N+1's run goes on, because N+1's head contains
  N's. If N goes red, the batch runner rebuilds N+1 from the base without N, and N's lane is
  fixed in its own lane.
  When the repo holds a standing merge grant (claude-settings record `standing-merge-grant`), it
  batches each PR whose review log is done, as `merge --reviewed` finds it at its wake. It merges
  the integration PR on green (until the cutover). It asks the owner for no merge. It prints the merge output on the
  terminal, never to a log only. A runner that merges a second checkout runs `~/.claude/bin/merge -C <checkout> <pr> --confirm`,
  never `cd X && merge`, and only when its own record names that checkout's repo (claude-settings record
  `merge-confirm-repo`). It runs the confirm in the foreground (Bash timeout up to 600000), never with
  `run_in_background`: a background call misses the allow rule and the auto-mode classifier refuses it. It dispatches no deferred step. Each CI or merge alarm wakes it, and it fixes the alarm or brings it to the coordinator (ruling R53). A red job wakes it at once (ruling R50). It runs Sonnet 5.5 at medium effort (ruling R52).
- **Lane.** Runs one line of work, with its own builder and reviewer agents.
  It opens its draft PR early, runs `merge --lane-lint <pr>` (with `--touched-tests` when it touches tests),
  posts the review record, then hands in to the batch runner (decision `session-tiers`). It ends with the
  four-point check, commits its handoff to `roadmap/outbox/<slug>-handoff.md` and tags itself archive-ready
  (ruling R46). The owner never reads a lane: it sends each owner act and question to its parent with the
  exact line. It ends with no step still doing under its id. It marks each part that is ruled but not built "ruled, not built".
  It reports up to the coordinator. Work that needs a local machine is a lane whose brief
  names the machine. It may drive a Remote Control session on the owner's machine.
- **Batch runner's standing duty: a rolling combine train.** The batch runner keeps it all the time (ruled, not built)
  (claude-settings decision `session-tiers`, bullet "Rolling combine train": the levels L1 to L4, what is
  frozen, what keeps folding, what a fold owes, the pre-flight step (relayed, not checked), and the per-batch report numbers).

When the owner names the wrong session, or brings work that belongs to another session, the session
says in one line whose job it is, then routes it.

A coordinator's work in another repo is compliance only, by handoff or by its own lane PR in that repo
(claude-settings decision `session-tiers`, bullet "A coordinator in another repo"). Before it acts,
it checks whether that repo has an active coordinator: a live session tagged both
`cs-repo:<other owner>/<other name>` and `cs-build:coordinator`. It reads every page of
`list_sessions` and filters the tags itself. If one is active, it coordinates with it.
If none is active, it proceeds. It does not wait for a reply.

## Rotation of standing sessions

Standing sessions compact in routine use, and none is replaced routinely: triage, the batch runner and the arbiter compact. Never wait for the owner to notice a stale one.

The coordinator itself does not rotate. It writes its own handoffs and compacts in place. The coordinator
never hands its own sessions to a successor: a session may refuse a new coordinator as not its
parent, or miss a message while busy.

- At each wake, the coordinator reads each standing session's use from `get_session`:
  `external_metadata.context_usage` (`used_tokens` of `max_tokens`). A reading of 0, or none,
  is no reading, and the use is unknown. No session reports its own tally (owner, 2026-11-02 15:40 CST).
- A standing session runs until autocompact. The coordinator rotates one only when it goes stale
  or breaks. A session breaks when it slips: a re-asked question, a reply that contradicts the
  roadmap, or a missed ruling (claude-settings decision `session-tiers`, owner, 2026-11-01 17:56 CST).
- On a rotation, in this order. The coordinator tells the session to rotate.
  1. The old session stops watching each page its role owns (the repo's one page, the project's
     waiting page): `ArtifactComments` action `watch` with `on: false` and the page URL. It notes
     the time from `~/.claude/bin/now-central --full`, then answers each comment still open at that time on those pages. From step 1 to
     step 5, `writer` in `meta/page` still names the old writer, and no writer watches the page.
     Asks sent then reach the new writer through its step-5 catch-up read and its first-turn read
     of `asks/`.
  2. It drains its work in flight: it starts nothing new, and ends or hands over each wait it holds.
  3. It writes the hand-off file, `handoffs/<role>-<date>.md` on the record branch, from
     `role-handoff.md`, with that time. The file names each wait it handed over, the home of
     the open waiting-page items (the items collection, by URL, never each item), and each page to watch. It runs
     `python3 ~/.claude/skills/project-ops/scripts/check_handoff.py <file>` on the file and
     fixes each problem before the successor starts.
  4. The coordinator archives the old session, then the coordinator starts the successor from the hand-off file
     and sends triage the new id in the same turn. Triage rewrites the roster line on the record
     branch (ruling R22). The coordinator sends no broadcast. Sessions read the roster.
  5. The successor watches each page at once (`ArtifactComments` action `watch`, on each `Watch:` URL),
     before any other act. It reads each page's comments since the time in the hand-off file.
     It rewrites `owner` on each inherited open item to itself. An item's `owner` is the session
     that reads the answer, so an item left with the old `owner` gets no reader. If it takes over
     the writer role, it also sets `writer` in `meta/page` to its own session title, as the roster
     gives it. It reads `meta/page` first, then updates `writer` pinned with `if_version`
     (`ArtifactData`). In a repo whose extras file holds the `page-writer` key, it also updates that
     key to its own session id. The key sits in a committed file, so the update goes in a PR. For each
     ask with no `reply` whose `owner` is the old writer, it reads the
     ask, then updates `owner` to itself, pinned with `if_version`. Only the incoming writer writes
     `writer`, since the outgoing one is archived at step 4.

## Autopilot

- Never wait on the owner. A step that needs the owner's answer gets a note line
  `Deferred (owner, <date>): <why>`, and waits. All other work runs, in roadmap order.
- A lane that hits a question for the owner parks that part, and goes on.
- A lane posts its review log on its PR after each round (claude-settings record
  `pr-review-record`). The batch runner finds it. The lane first runs `merge --lane-lint <pr>`. The batch
  runner runs it again on each lane head before the join, and refuses a red lane (claude-settings record
  `lanes-run-no-full-ci-job`). A lane never rebases onto main and never merges. After a batch merges, a handed-in PR that conflicts with the new main gets one main merge by its lane (step `post-batch-conflict-merge`; whether a review of only the resolved hunks suffices is the owner's open item 651).
- A record that files an owner ruling gets a round 1 review before it merges. Round 1 checks two things only (claude-settings decision `docs-only-prs-skip-review`).
- Nobody pushes to a PR's head once a done review log is posted for that head, until the merge
  result is back. The exception is the fix that a FAIL round calls for, such as the round-1 fix on a
  `delete-only` change with Guard or check `no`, which reads done (claude-settings record
  `pr-review-record`). That push makes the record stale, so the lane posts a new review log for the
  new head. When the repo holds a standing merge grant, the batch runner merges under it. The owner is
  not asked.
- A session that waits on CI sets a one-time check-in when it starts to wait, and again after each red job, each wider apart.
- Stall check: at each wake, a standing session asks whether any lane, PR or batch moved since its last
  turn. When none moved and work is ready, it finds why and acts, or tells the owner what blocks it.
  A turn that ends waiting on a named event sets a one-time check-in for that event. It sets the next one only when a new named event arrives, such as a red job, never on a wake from anything else.
- A check-in's message names the home of each list it reads (a page collection, a roadmap ref, a git
  ref or a GitHub query), never a copy.

## Filing

- A message can hold a ruling, a finding, a new step, a debt or a note. File it in the same turn,
  and tell the owner in one line where it went.
- Only triage writes new steps, merges, order and closes. Another session sends the item to triage,
  with the owner's message attached.
- Owner feedback about another repo goes to that repo's triage, with the owner's message attached
  (decision owner-feedback-inbox, one feedback inbox per repo).
- A session rewrites the note, status and brief of a step it works on.
- The roadmap is a current record, not a log. Rewrite a note to what is true now. Keep each ruling
  as one dated line.
- A new or moved step near the top gets the line `Placed ahead of <step> (triage, <date>): <why>`.
- Pull right before each write.

## Messages between sessions

- Send a message at once in two cases: work is blocked (a PR held, a lane stopped), or the owner
  asked for something to be passed on.
- The git mailbox carries a message: `mail send`, with `mail wait` as the doorbell (skill `waiting-page`,
  `reference/routing-and-sessions.md`; decision `session-messages`).
- Send non-urgent notes, findings and filing requests to the outbox: `roadmap/outbox/<session-slug>.md`
  on the record branch. Each session keeps one file and rewrites it to hold only what is unfiled.
- Triage reads the outbox at each wake, files each item, and removes what it filed. A `*-handoff.md` file is the exception: it stays as the reference for an archived session (ruling R46).
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
