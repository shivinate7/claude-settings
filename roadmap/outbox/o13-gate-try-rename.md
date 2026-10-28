# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28 12:40 UTC, step o13): PR #746 head b94933b2 (pushed, draft) includes main a64166ae (batch 7). A fresh review of the batch 7 merge passed (reviewer sonnet). The local checks are green, except the load-brake probe case, which fails on main too.
- Waiting: batch 8 (#767) merges first. If it lands, merge main again (merge commit), rename any new gate or try uses, re-run the checks, push, then message the orchestrator. The orchestrator then takes #746 to shiv for the protection switch (waiting-page item 33).
