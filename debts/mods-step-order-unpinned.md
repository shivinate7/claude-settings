# No test pins that the mod test step is last

- **What.** No test pins that the mod test step is last. If a mod test fails, a step added after it is skipped. The job stays red, so the verdict is right.
- **Where.** The step order in the `gates` job of `.github/workflows/gates.yml`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** A pin in `lint/test_harness_scope.py` fails on any step placed after the mod test step.
