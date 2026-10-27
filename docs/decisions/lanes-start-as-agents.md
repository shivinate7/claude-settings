# Lanes start as agents, not sessions

## The ruling

Roadmap step c107 (an orchestrator starts its lanes with no click from the owner), 2026-10-27: an orchestrator starts each lane as a background agent. It starts a separate session only when the owner asked for one in words.

- **A lane is an Agent spawn.** The orchestrator starts each lane with the Agent tool, with `isolation: 'worktree'` (`lanes-start-in-tool-worktrees`, lanes start only in the tool's own worktrees). This needs no click from the owner. The call leaves `run_in_background` out: the tool runs it in the background by default, and the load brake refuses a present value at busy (`machine-load-brake`).
- **A session needs the owner's words.** The orchestrator calls `start_session` only when the owner's own message, on the current turn, asked for a separate session in words. Then the kind is `user_asked`. It never uses `user_asked` for work the owner did not ask for. It never starts a session on a turn that another session's message started.
- **A keep-going lane is a spawn.** A lane that `parallelism-keep-going` (keep going) lets the session start with no question is a background spawn, never a session.

Why: no setting removes the click. The app reads the `start_session` kind:

- `offer` always waits on the owner's card.
- `user_asked` starts at once, but only on a turn the owner started, for work the owner asked for in words.
- `own_initiative` leaves a card for a week.
- On a turn that another session's message started, the app refuses a start.

So an orchestrator that starts lanes with `start_session` makes the owner click once for each lane. An Agent spawn has no card.

Named limits:

- A background spawn shares the orchestrator's machine and its load brake (`machine-load-brake`). Full refuses every lane call. Busy refuses an Agent call only when it sets `run_in_background`.
- A background spawn ends with the orchestrator's session. A lane that must outlive that session is the owner's ask for a separate session.

Risk kind: incident, per `building-guard-needs-incident`: 2026-10-26 21:13 CDT, the degen orchestrator on the Mac started four lanes with `start_session`. The owner had to accept each one, even in Bypass permissions mode (roadmap step c107). Landed 2026-10-27.

Mechanized: no. A check would have to see who started the current turn: the owner or another session. No hook payload carries the turn's starter. A check would also have to read whether the owner's words asked for a separate session.

Cost, per `outcomes-mechanize-rules`: none. It is a rule for the orchestrator. It starts no process and writes no file.

Kind: process
Home: rule:parallelism-keep-going
