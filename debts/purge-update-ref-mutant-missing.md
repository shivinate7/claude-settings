# The mutation harness has no mutant for the update-ref commit argument

- **What.** The harness has no mutant that drops only the commit argument of `update-ref -d`. The harness alone does not catch that change. A hand run of the change was killed by `test_a_reap_landing_after_the_read_keeps_the_younger_ref`. The row "the ref is dropped by branch name" in `janitor/mutate_sweep.py` may drop that argument, with a different named killer. This is unverified.
- **Where.** The mutant rows in `janitor/mutate_sweep.py`.
- **Decision.** `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).
- **Retire.** A mutant row drops only the commit argument, and it goes red on a named case.
