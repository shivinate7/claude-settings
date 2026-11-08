# The revival read cannot see a rebase, squash or cherry-pick

**What.** A lane that is rebased, squashed or cherry-picked onto main leaves no merge commit. The revived-line read of the silent-undo check looks only at merge commits, so it cannot see a deleted note row come back there. Claude can hit it with `git pull --rebase`.

**Where.** `lint/check_silent_undo.py`, `revived_lines` and its loop over `rev-list --merges` in `check`.

**Decision.** `silent-undo-check-design`, one check catches a merge or branch that silently undoes earlier work. It lists this as a known limit.

**Retire.** Read a rebased, squashed or cherry-picked lane for a row that a union file brings back. Add a case that goes red on the old check, and prove it with `lint/test_check_silent_undo.py`. A read that flags a plain rebase with no revival reopens this debt.
