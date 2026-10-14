# Other blind-git fixtures are not audited for the PATH shim gap

- **What.** The entry does not audit every blind-command fixture in the repository for the PATH shim gap. `make_blind_git` in `janitor/test_sweep.py` may carry the same assumption. That audit is not part of the change that made the entry.
- **Where.** `make_blind_git` in `janitor/test_sweep.py`, and the other blind-command fixtures.
- **Decision.** `list-form-subprocess-ignores-a-path-shim-on-windows` (a list-form subprocess call ignores a PATH shim on Windows).
- **Retire.** Each blind-command fixture is audited. An arm that depends on the shim skips on Windows with the reason, or the audit records that none does.
