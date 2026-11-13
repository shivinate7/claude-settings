---
paths:
  - "hooks/**"
  - "janitor/**"
---

# Hooks and janitor

Rule `outcomes-mechanize-rules` (root CLAUDE.md) lets tracking read on demand, inside a process already running. It never allows a read on every tool call. A timer is allowed only when its record shows it costs less than it saves. An allowed timer starts no new long-lived process. Watching must cost less than what it watches.

The named exceptions follow. Each states its cost in its decision record. Each has one status:

- **Met:** the record states the cost, a test proves it, and the exception fits the rule.
- **Open:** the exception does not fit the rule yet, or an owner ruling is pending.
- **Unmeasured:** the cost is stated, but no test or measure shows it, or the saving is not measured.

- **Load brake.** Locally, an agent's own write may read the machine load once, inside the guard hook already running for it. So may the own write of a session with an own id, to brake a lane session (decision `machine-load-brake`, the machine-load brake). Status: unmeasured. The record names family `load-brake` in `hooks/test_guard.py` for its counts. This lane did not confirm that the family pins the reads.
- **Stall watcher.** One watcher process per background shell call (decision `stall-watch`, the stall watch). Owner ruling, Cockpit item 180 (watchers: events only, named exceptions), pick a, 2026-11-06 12:19 CST, keeps it. Status: open. The watcher lives as long as its job, which the rule's "no new long-lived process" does not allow. The owner ruling on that is pending (step `watchers-plan-lanes`).
- **CI wake.** One `hooks/ci_wake.py` watch per `gh pr ready` (decision `ci-wait-reads-run-status`, CI waits read the run status). Same ruling. Status: open, for the same reason. The watch lives up to its 3300 s budget.
- **Daily job.** One scheduled sweep a day (decision `the-janitor-is-one-machine-wide-sweep`, the janitor). Same ruling. Status: unmeasured. The install's cost is pinned by tests. The saving is not measured, so the rule's timer condition is not shown.

A model-call hook is not an exception. Each one is a child inside its own hook budget (decision `haiku-prompt-hooks`).
