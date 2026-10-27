# The merge tool's foreground shell exits with no reason while its merge lives on

- **What.** Twice on 2026-10-20 (#527 in the afternoon, #538 at 00:08 CDT on 10-21), the background shell that ran `bin/merge <pr> --confirm` exited rc 1 mid-wait and printed no reason. The merge process lived on and held the merge lock. A rerun printed "the merge lock on main is held by PR #538 ... pid 2068168 ... The holder is alive". The caller gets no completion notice for the real outcome.
- **Where.** `merge/merge.py`, the wait loop or its process launch.
- **Decision.** `standing-merge-grant` (the repo grant that lets the orchestrator merge by pull request). It does not name this gap.
- **Retire.** The foreground process exits only with the merge's real outcome, or prints why it handed off. A test pins it.
