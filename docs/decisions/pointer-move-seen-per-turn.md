# A pointer checkout moved off main is flagged at each Stop

## The ruling

Coordinator, 2026-11-09 12:18 CST, chose option b.

Question: how does a move of the pointer checkout off main, made during a session, get seen?

- The Stop watch reads the pointer checkout's HEAD once per turn, after the sweep.
- It prints a flag when the branch is not main.
- It prints a flag for a detached HEAD that is not at local main's commit or at origin/main's tip.
- An unreadable HEAD prints the unknown line.
- A folder with no `.git`, and a global rules file with no `@` line, stay silent.

Option a, a guard that refuses `update-ref` and `reset` on the pointer checkout, was not taken. It would also block a legitimate reset on main. It also misses a mover that is unknown.

## Incident

Lane notes-fix-large-1 ran on a pointer checkout detached at an old merge (2026-11-07 20:03 UTC to 2026-11-09 11:40 CST). `session_start.sh` (the session start hook) reports only at session start. The mover was never found.

## Harm stopped

Every hook, lint and agent runs old code, unseen.

## Cost

Per rule `outcomes-mechanize-rules`:

- At most 4 `git rev-parse` calls per Stop. One call when the pointer is on main.
- No file written. No new process or timer. The read runs inside the Stop hook already running.
- The test row `row_cost_stop_read_count` pins the call count.

Kind: process
Home: rule:outcomes-mechanize-rules
Home: hooks/config_watch.py
