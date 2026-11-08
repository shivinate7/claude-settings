# A merge reason that ends in `)` hides the merge's flags from the guard

**What.** The merge-confirm-repo clause stops reading a merge's arguments at the first token that ends in `)` or `&`. It reads the tokens after shlex has dropped the quotes, so a quoted reason that ends in `)` cuts the arguments too. Then `-C /other` or `--confirm` after the reason is not read. Two cases: `merge 5 --confirm --base-red-ok "flaky (x)" -C /other` is judged in the cwd repo, and `merge -C /other 5 --base-red-ok "flaky (x)" --confirm` is not judged. Reason text that ends in `)` is common prose.

**Where.** `hooks/guard_merge.py`, `_command_words` and its use in `_unproved_confirm`.

**Decision.** merge-confirm-repo (a cloud merge acts only in a repo its own record names).

**Retire.** The clause reads the `)` or `&` ending from the raw segment text, not from the unquoted tokens. A case in `hooks/test_guard.py` denies both commands above when the own record names only the cwd repo.
