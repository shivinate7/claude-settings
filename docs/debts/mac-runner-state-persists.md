# Same-repository pull request code runs on the Mac as the guest account, and its files persist

- **What.** Code from a same-repository pull request runs on the owner's Mac as the runner's guest account, not the owner's main account. The runner's `_work` folder and the account's home files persist across jobs. The runner's credentials are readable by that account. Whether a job can reach the Mac's local network is unknown.
- **Where.** The runner registered on the owner's Mac, with labels `self-hosted`, `macOS`, `ARM64` and `claude-settings-mac`. The `run` job of `.github/workflows/lane-touched-tests.yml` names it through the variable `MAC_RUNS_ON`.
- **Decision.** `mac-runner-try` (the owner's try that lets the macOS leg use the Mac).
- **Retire.** The owner's larger plan: a clean account, or an ephemeral runner for each job.
