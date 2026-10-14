# Rebase loss before the rebase base goes unread

- **What.** After a rebase, the silent-undo window starts at the rebase base. A rebase that took its own side and lost main work older than that base is not read.
- **Where.** `check()` in `lint/check_silent_undo.py`, where it finds the fork point.
- **Decision.** `silent-undo-check-design` (one check catches a merge or branch that silently undoes earlier work). Its "Holes, named" section names this gap.
- **Retire.** Find the window start from the branch's cut before the rebase, with no clock. A test that rebases past two main commits and loses the older one goes red.
