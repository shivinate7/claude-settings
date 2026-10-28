# o13 lane A: the gate/try rename (redo of PR #639)

- Next: when the orchestrator says #774 (step c181, batch 11) has merged, merge main again (merge commit), rename any new gate or try uses, re-run the checks, push, mark #746 ready so CI runs, then message the orchestrator. The merge also waits for shiv's protection switch (waiting-page item 33).
- Status (Oct 28 14:30 UTC, step o13): PR #746 head 9b1e59a7 includes main abf9259f. With pipx installed (`pip install --user pipx`, ~/.local/bin first on PATH), `ci-job checks --lint` passes on every step, Code check included. Waiting for #774 (batch 11).
