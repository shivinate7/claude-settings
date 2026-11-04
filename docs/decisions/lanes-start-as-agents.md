# A lane is a session, local and cloud alike

## The ruling

Owner, 2026-11-04 07:56 CST, waiting-page item 168 (what a lane is), pick a: a lane is a session everywhere. The same team of sessions (coordinator, triage, batch runner, lane sessions) runs all on the owner's Mac or all in the cloud, as one concept. The owner asked (2026-11-03 22:26 CST) why an all-local run and an all-cloud run of the same sessions could not share one concept. The owner saw no reason for the cloud and the Mac to mean different things.

- **A lane is the unit of work.** It has its own branch, worktree and lane PR. A lane session runs it, local and cloud alike. The GLOSSARY lane row defines it.
- **The coordinator starts each lane session.** Inside a standing build the owner started, it needs no further owner grant (record `session-tiers`, A coordinator starts lane sessions).
- **An agent is not a lane.** A solo, one-lane or lane session fans its own work out to agents, each in its own worktree (`parallelism-each-own-checkout`, each agent in its own checkout). That work is part of the session's lane, or of its solo task.
- **A Mac start, until the probe answers.** On the Mac, one session that starts another shows the owner a card to press, and the card drops the lane's branch (incident below). Until a probe answers, each Mac lane start is one press, and the lane brief makes the lane set its own branch first thing.
- **The probe.** A session on the owner's Mac measures two facts on that day's Claude version: whether the card still shows, and whether it still drops the branch. A cloud session cannot see the Mac card. The coordinator starts the probe as a lane of its own. Its result rewrites the bullet above.

Why: one name, one meaning. Two meanings of "lane" made the records disagree (debt `page-answer-second-click`, a page answer needs a second approval). In the cloud a coordinator starts lane sessions with no card (more than 30 since 2026-11-01). The card is the one measured difference, and it costs one press per Mac lane.

Incidents:

- 2026-10-26 21:13 CDT: the degen orchestrator on the Mac started four lanes with `start_session`. The owner had to accept each one, even in Bypass permissions mode.
- 2026-11-02 11:18 CST: three lane cards on the apartment run dropped `source_branch` and `branch_name`. Two lanes started from main, not from their branch.

Mechanized: no. A check would have to tell a lane session from an agent at the point it starts. The start call carries no lane marker.

Cost, per `outcomes-mechanize-rules`: none. It is a rule for the coordinator. It starts no process and writes no file.

Kind: process
Home: rule:parallelism-own-lane-orchestrator
