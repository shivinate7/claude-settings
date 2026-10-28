# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28 10:00 UTC, step o13): PR #746 head 929886a9 (pushed, draft) includes main 646d23c5 (batch 5). Batch 5's janitor "gate" wording is renamed to check. Local checks are green, except the load-brake probe case, which is red on main too. Three review rounds passed earlier.
- Paused: #746 waits for batch 7 (batch 6 merged at main 599dd58b). When the orchestrator says batch 7 merged, merge main again (merge commit), rename any new gate or try uses, re-run the checks, push, then message the orchestrator. The PR merges alone with shiv's protection switch (waiting-page item 33).
