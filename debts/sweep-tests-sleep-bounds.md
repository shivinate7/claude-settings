# Two sweep tests still lean on a sleep

- **What.** `_peak_concurrency` sleeps 0.2 s inside each wrapped call to widen a race. The confirm test then asserts a peak of 1. On a slow host, two parallel calls can miss each other, so a mutant that runs confirm in parallel can survive. Some other tests poll with a 0.2 s sleep until a pid or a folder is gone. A poll waits for a state and asserts no time, so it is not a timing check.
- **Where.** `_peak_concurrency` and its confirm test in `janitor/test_sweep.py`.
- **Decision.** `test-strategy-reset` (keep one row; no test times a run on a local device).
- **Retire.** Replace the sleep with an event hand-off: the first wrapped call waits until a second call starts, or until a short hang guard ends. Show the parallel-confirm mutant red 20 of 20.
