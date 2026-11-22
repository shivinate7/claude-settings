# A lane's confirm can carry the red-main and unknown-read flags

**What.** A lane's `merge --confirm` runs only on its own ready pull request, but nothing refuses it the flags `--base-red-ok`, `--undo-check-unknown-ok` and `--express`. I found no lane-role check beside those flags in `merge/merge.py` (only the closing-reason check). Mistake: a lane adds one of them to get past a refusal. Harm: the lane merges past an UNKNOWN main or an unread silent-undo check, with no batch runner or owner in the loop. Reported 2026-11-15 (lane lane-merges-own-pr-code); not run.

**Where.** `merge/merge.py`, the confirm path of a lane-tagged session (`MERGE_ROLES`, `refuse_closing_reason`).

**Decision.** `no-merge-onto-red-main` (a PR may merge onto a red main; UNKNOWN still refuses, and `--base-red-ok` lifts only an UNKNOWN read).

**Retire.** A lane-tagged `--confirm` refuses those three flags. A case in `merge/test_merge.py` runs each flag as a lane and expects a refusal, red without the guard.
