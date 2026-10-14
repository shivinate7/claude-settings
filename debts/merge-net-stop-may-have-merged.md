# The NetStop text says run again after a possible merge

- **What.** The NetStop text says "Run again." The merge may have landed. A rerun stops at "is MERGED". The after-merge steps (`ff_main`, `afterMerge`, `cut_branch`) do not run.
- **Where.** The NetStop text in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does on a network error).
- **Retire.** The NetStop text checks for a landed merge before it says run again, and a case pins it.
