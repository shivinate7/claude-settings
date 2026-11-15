# A sim-lease edit runs no guard mutation job on its PR

- **What.** The CI scope routes `bin/sim-lease` to the shell-macos and code jobs only. It is a guard mutation target (`simlease` in `hooks/mutate_guard.py`), so a PR that edits it runs no guard mutation job, and a stale mutant turns main red after the merge.
- **Where.** `.github/scripts/ci-scope.sh`, the `bin/sim-test|lint/test_sim_test.sh|bin/sim-lease` arm.
- **Decision.** none.
- **Retire.** Route `bin/sim-lease` to the guard flag too, and add a case that shows it. `lint/test_ci_scope.py`
