# A report can call main's state unknown without reading main

**What.** A report can call main's state unknown without first reading main's newest run. Before a report calls main's state unknown, it must read main's newest run by REST. Incident: 10:23 CST Nov 19. Queued step `main-state-read-by-rest`, queued in chat on Nov 18-19.

**Where.** `lint/report_guard.py`, the report gate. It checks no report's claim about main's state. The read it needs is main's newest finished run. The merge tool already reads that run in its `main-run` phase (`merge/merge.py`, decision `merge-phase-timing`).

**Decision.** `no-merge-onto-red-main` (main's newest finished run decides whether main is red).

**Retire.** `lint/test_report_guard.py` holds a case, red first on the current code, where a report that calls main's state unknown, with no read of main's newest run, is refused by the report gate.
