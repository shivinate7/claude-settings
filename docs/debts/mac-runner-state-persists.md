# Same-repository pull request code runs on the Mac as the guest account, and its files persist

- **What.** Code from a same-repository pull request runs on the owner's Mac as the runner's guest account, not the owner's main account. The runner's `_work` folder and the account's home files persist across jobs. The runner's credentials are readable by that account. Whether a job can reach the Mac's local network is unknown.
- **Where.** The runner registered on the owner's Mac, with labels `self-hosted`, `macOS`, `ARM64` and `claude-settings-mac`. The `run` job of `.github/workflows/lane-touched-tests.yml` names it through the variable `MAC_RUNS_ON`.
- **Decision.** `mac-runner-try` (the owner's try that lets the macOS leg use the Mac).
- **Likely mistake.** A lane step that writes outside the checkout. The map leg's `npm ci` writes `node_modules` into the checkout, and its npm cache sits under the account's home by default (unverified on this runner). Or an outside contributor's patch applied into a same-repository draft, which skips the fork approval hold.
- **Retire.** The owner's larger plan: a clean account, or an ephemeral runner for each job.
