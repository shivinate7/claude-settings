# Nothing reads the fork pull request setting that guards the Mac

- **What.** The Mac runner is safe from fork code only while the repository's Actions setting for fork pull request workflows is `all_external_contributors` (read by REST at 14:05 CST Nov 25 2026). Nothing reads that setting. A weaker value would let a fork's workflow file name the Mac runner, so fork code could reach the Mac.
- **Where.** The repository's Actions permissions, at `actions/permissions/fork-pr-contributor-approval`. The Mac is named by the `run` job's `runs-on` in `.github/workflows/lane-touched-tests.yml`, through the variable `MAC_RUNS_ON`.
- **Decision.** `mac-runner-try` (the owner's try; it names this setting as the guard).
- **Retire.** A daily check reads the setting by REST and goes red when it is not `all_external_contributors`. Or the runner moves to a runner group that fork pull requests cannot use.
