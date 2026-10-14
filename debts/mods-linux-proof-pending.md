# The mod tests have no CI run on Linux yet

- **What.** The builder ran the mod tests on Windows only. The Linux runs were made in WSL through the owner's own terminal: plain-diff 72 of 72, session-board 119 of 119, on Node v22.23.1. Those runs are not CI runs. The WSL rule comes from decision `wsl-allow-list`. The first CI run on Linux is the real proof.
- **Where.** The mod test step in the `gates` job of `.github/workflows/gates.yml`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The first CI run on Linux is green. A red Linux test is re-pointed, and never skipped.
