---
paths:
  - "hooks/**"
  - "janitor/**"
---

# Hooks and janitor

Rule `outcomes-mechanize-rules` (tracking reads on demand inside a process already running, never on a timer or on every tool call) has four named exceptions. No other mechanism may start a timer, a poll or a long-lived process. Each exception states its cost in its record, and a test proves it.

- **Load brake.** Locally, an agent's own write may read the machine load once, inside the guard hook already running for it. So may the own write of a session with an own id, to brake a lane session (decision `machine-load-brake`, the machine-load brake).
- **Stall watcher.** One watcher process per background shell job (decision `stall-watch`, the stall watch). Owner, Cockpit item 180, pick a, 2026-11-06 12:19 CST.
- **CI wake.** One `hooks/ci_wake.py` watch per `gh pr ready` (decision `ci-wait-reads-run-status`, CI waits read the run status). Same ruling.
- **Daily job.** One scheduled sweep a day (decision `the-janitor-is-one-machine-wide-sweep`, the janitor). Same ruling.
