# --check --base judges only the first line of a statement

- **What.** A finding is keyed to the first line of its statement. A changed bound on an old multi-line assert, or a new clock read above an old one-line assert, adds no finding line, so `--check --base` passes a time-pinned line the branch changed.
- **Where.** `lint/find_time_pinned.py`: the Limit sentence in the module docstring, and `report_new_only`. A three-line `assert (` reports its first line, so a change to its bound line is not judged.
- **Decision.** `test-strategy-reset` (point 2: no timed wait on a fixed sleep or a wall-clock bound).
- **Retire.** `lint/test_find_time_pinned.py` has cases where a changed bound on an old multi-line assert, and a new clock read above an old one-line assert, each make `--check --base` exit 1.
