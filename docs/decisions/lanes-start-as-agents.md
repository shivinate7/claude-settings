# A lane is a session, local and cloud alike

## The ruling

Owner, 2026-11-04 07:56 CST, waiting-page item 168 (what a lane is), pick a: a lane is a session everywhere. The same team of sessions (coordinator, triage, batch runner, lane sessions) runs all on the owner's Mac or all in the cloud, as one concept. The owner asked (2026-11-03 22:26 CST) why an all-local run and an all-cloud run of the same sessions could not share one concept. The owner saw no reason for the cloud and the Mac to mean different things.

- **A lane is the unit of work.** It has its own branch, worktree and lane PR. A lane session runs it, local and cloud alike. The GLOSSARY lane row defines it.
- **The coordinator starts each lane session.** Inside a standing build the owner started, it needs no further owner grant (record `session-tiers`, A coordinator starts lane sessions).
- **An agent is not a lane.** A solo, one-lane or lane session fans its own work out to agents, each in its own worktree (`parallelism-each-own-checkout`, each agent in its own checkout). That work is part of the session's lane, or of its solo task. An agent ends with the session that started it.
- **A keep-going follow-up.** A follow-up that `parallelism-keep-going` (keep going) lets a session start with no question is an agent when it is part of the session's own topic. A follow-up on a new topic is a new lane, so it goes to the coordinator. A solo session has no coordinator: it starts the follow-up as an agent and names it under Done.
- **A session starts another only on the owner's words.** Outside a coordinator, a session calls `start_session` only when the owner's own message, on the current turn, asked for a separate session in words. Then it passes `initiation: user_asked`. It never uses `user_asked` for work the owner did not ask for.
- **A Mac start.** The card is the desktop app's own. No setting, allow rule or hook removes it: it showed in Bypass permissions mode, where allow rules have no effect. Probe of 2026-11-06 13:55 CST (owner, waiting-page item 296, Claude 2.1.296 desktop):
  - Kind `user_asked`, on a turn the owner typed: no card, and the session starts. Two of two starts.
  - Kind `offer`: a card, and the session does not start until the owner presses. `offer` takes no `source_branch`.
  - The source branch name is not kept. Each `user_asked` start gets a new worktree branch, such as `claude/nervous-panini-ef0139`. Whether that branch is cut from the source branch is unmeasured: the source branch equalled main.
  - So a coordinator in a standing build the owner started passes `user_asked` on every lane start (owner, 2026-11-06 14:01 CST, waiting-page item 297: kind `offer` was the one reason for the card). The lane brief makes the lane set its own branch first thing.
- **The next probes.** A session on the owner's Mac measures two open cases. First: a `user_asked` start with a source branch one commit ahead of main, and whether the new worktree branch holds that commit. Second: a `user_asked` start on a turn that a wake started, not the owner's typing, and whether it shows a card or is refused. A coordinator's lane starts often fall on such turns. Each result rewrites its line above. A card in the second case brings the owner a question.

Why: one name, one meaning. Two meanings of "lane" made the records disagree (debt `page-answer-second-click`, a page answer needs a second approval). In the cloud a coordinator starts lane sessions with no card. On the Mac, a start with kind `offer` shows a card, and a `user_asked` start on the owner's turn does not.

Incidents:

- 2026-10-26 21:13 CDT: the degen orchestrator on the Mac started four lanes with `start_session`. The owner had to accept each one, even in Bypass permissions mode.
- 2026-11-02 11:18 CST: three lane cards on the apartment run dropped `source_branch` and `branch_name`. Two lanes started from main, not from their branch.

Mechanized: no. A check would have to tell a lane session from an agent at the point it starts. The start call carries no lane marker.

Cost, per `outcomes-mechanize-rules`: none. It is a rule for the coordinator. It starts no process and writes no file.

Kind: process
Home: rule:parallelism-own-lane-orchestrator
