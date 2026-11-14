---
paths:
  - "hooks/**"
  - "janitor/**"
---

# Hooks and janitor

Rule `outcomes-mechanize-rules` (root CLAUDE.md) lets tracking read on demand, inside a process already running. It never allows a read on every tool call. A timer is allowed only when its record shows it costs less than it saves. An allowed timer starts no new long-lived process. Watching must cost less than what it watches.

Owner ruling `stall-watch-exceptions-180a` (page item 180, Cockpit item 180, pick a, 2026-11-06 12:19 CST) names three exceptions to that rule: the stall watcher, CI wake and the daily job. Each has a stated cost in its decision record and a cost test. Root CLAUDE.md does not name them yet (step `claude-md-timer-exceptions`, pending the owner's exact text).

Each exception has one status:

- **Ruled:** named by ruling `stall-watch-exceptions-180a`, with a stated cost and a cost test.
- **Unmeasured:** the cost is stated, but no test or measure shows it, or the saving is not measured.

- **Stall watcher.** One watcher process per background shell call (decision `stall-watch`, the stall watch). Status: ruled. The watcher lives as long as its job.
- **CI wake.** One `hooks/ci_wake.py` watch per `gh pr ready` (decision `ci-wait-reads-run-status`, CI waits read the run status). Status: ruled. The watch lives up to its 3300 s budget.
- **Daily job.** One scheduled sweep a day (decision `the-janitor-is-one-machine-wide-sweep`, the janitor). Status: ruled. Its saving is unmeasured, so the rule's timer condition is not shown.

The load brake is not one of the three. Locally, an agent's own write may read the machine load once, inside the guard hook already running for it. So may the own write of a session with an own id, to brake a lane session (decision `machine-load-brake`). Status: unmeasured. No cost test is confirmed: the record names family `load-brake` in `hooks/test_guard.py` for its counts, and that family's pinning of the reads is not verified.

The doorbell (`mail wait`) is a waiting process beside these three, not one of them. Its record is the doorbell section of decision `session-messages` (ruling 3.15, owner 2026-11-11 13:22 CST). That section names cost test `test_the_decision_states_the_measured_doorbell_cost` in `hooks/test_mail_wait.py`.

A model-call hook is not an exception. Each one is a child inside its own hook budget (decision `haiku-prompt-hooks`).
