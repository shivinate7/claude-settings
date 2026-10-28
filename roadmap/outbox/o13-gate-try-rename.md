# o13 lane A: the gate/try rename (redo of PR #639)

- Status (Oct 28 10:00 UTC, step o13): PR #746 head 929886a9 (pushed, draft) includes main 646d23c5 (batch 5). Batch 5's janitor "gate" wording is renamed to check. Local checks are green, except the load-brake probe case, which is red on main too. Three review rounds passed earlier.
- Paused: #746 goes after batch 6 (#760). When #760 merges, merge main again (merge commit), rename any new gate or try uses, re-run the checks, push, then message the orchestrator. The PR merges alone with shiv's protection switch (waiting-page item 33).
