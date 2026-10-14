# Off-line fork point reads main work from before the cut

- **What.** When a branch is cut from a PR branch that merged later, its fork point is off upstream's first-parent line. The `+1` in the silent-undo window then reads the first-parent commit below that PR's merge. That is main work from before the cut, so a deliberate removal of it is flagged.
- **Where.** `check()` in `lint/check_silent_undo.py`, the `+1` in the window count.
- **Decision.** `silent-undo-check-design` (one check catches a merge or branch that silently undoes earlier work). Its "Holes, named" section names this gap.
- **Retire.** Read the fork commit itself when the fork point is off the line. A test that cuts a branch from a PR branch and removes older main work stays green.
