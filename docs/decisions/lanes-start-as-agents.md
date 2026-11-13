# A lane is a session, local and cloud alike

## The ruling

Owner, 2026-11-04 07:56 CST, waiting-page item 168 (what a lane is), pick a: a lane is a session everywhere. The same team of sessions (coordinator, triage, batch runner, lanes) runs all on the owner's Mac or all in the cloud, as one concept. The owner asked (2026-11-03 22:26 CST) why an all-local run and an all-cloud run of the same sessions could not share one concept. The owner saw no reason for the cloud and the Mac to mean different things.

- **Roles, the same on local and cloud** (owner, 2026-11-10 14:23 CST, G2: "coordinator approved", "batch runner yes agreed", "lane yes agreed but solo should be able to merge ideally like it can be a one stop shop sometimes", "this collapse feels good"). Solo, one lane and lane session collapse into one role, lane. Not built: the code and guards still name the old sessions.
- **A lane is the unit of work.** It has its own branch, worktree and lane PR. A lane runs it, local and cloud alike. The GLOSSARY lane row defines it.
- **The coordinator starts each lane.** Inside a standing build the owner started, it needs no further owner grant (record `session-tiers`, A coordinator starts lanes).
- **An agent is not a lane.** A lane fans its own work out to agents, each in its own worktree (`parallelism-each-own-checkout`, each agent in its own checkout). That work is part of the lane. An agent ends with the session that started it.
- **A keep-going follow-up.** A follow-up that `parallelism-keep-going` (keep going) lets a session start with no question is an agent when it is part of the session's own topic. A follow-up on a new topic is a new lane, so it goes to the coordinator. A lane with no coordinator above it starts the follow-up as an agent and names it under Done.
- **A session starts another only on the owner's words.** Outside a coordinator, a session calls `start_session` only when the owner's own message, on the current turn, asked for a separate session in words. Then the kind is `user_asked`. It never uses `user_asked` for work the owner did not ask for. The app refuses a start on a turn that another session's message started.
- **A Mac start, until the probe answers.** On the Mac, one session that starts another has shown the owner a card to press, and the card has dropped the lane's branch (incidents below). Until a probe answers, each Mac lane start is one press, and the lane brief makes the lane set its own branch first thing.
- **The probe.** A session on the owner's Mac measures two facts on that day's Claude version: whether the card still shows, and whether it still drops the branch. A cloud session cannot see the Mac card. The coordinator starts the probe as a lane of its own, because only the coordinator starts sessions (record `session-tiers`, Who starts which session). Its result rewrites the bullet above.

Why: one name, one meaning. Two meanings of "lane" made the records disagree (debt `page-answer-second-click`, a page answer needs a second approval). In the cloud a coordinator starts lanes with no card. The card is the one difference seen so far, and the probe measures it.

Incidents:

- 2026-10-26 21:13 CDT: the degen orchestrator on the Mac started four lanes with `start_session`. The owner had to accept each one, even in Bypass permissions mode.
- 2026-11-02 11:18 CST: three lane cards on the apartment run dropped `source_branch` and `branch_name`. Two lanes started from main, not from their branch.

Mechanized: no. A check would have to tell a lane from an agent at the point it starts. The start call carries no lane marker.

Cost, per `outcomes-mechanize-rules`: none. It is a rule for the coordinator. It starts no process and writes no file.

Kind: process
Home: rule:parallelism-own-lane-orchestrator
