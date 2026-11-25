---
id: pending
slug: mac-runner-try
---

# The macOS leg may run on the owner's self-hosted Mac, as a try

## The ruling

Owner, 13:18 CST Nov 25 2026, typed in the consultant's chat. His self-hosted Mac runner is its own guest account on his Mac, not his main account. It is not always on. He wrote: "feel free to give it a shot if it seems faster sure use it for now and if not then don't". He also wrote: "we can carve out a larger plan on it when i'm back for now im allowing u to freestyle it on the runner".

The try: the macOS leg of `lane-touched-tests.yml` (the `run` job) may run on that Mac. The repository variable `MAC_RUNS_ON` is the switch. This decision holds the question of where the macOS leg runs. Decision `draft-until-reviewed` holds the draft gate and the leg's file selection, and points here.

## What the workflow does

At head `e684473c18`, pull request 3950:

- The `run` job's `runs-on` reads `MAC_RUNS_ON` for a same-repository pull request. The macOS leg runs on the label that the variable holds.
- Unset or empty means hosted: the macOS leg runs on `macos-latest`.
- The Windows leg never reads the variable. The `touched` job runs on Linux.
- On: `gh variable set MAC_RUNS_ON --body <label>`. Off: `gh variable delete MAC_RUNS_ON`.
- The value is the runner's own label, `claude-settings-mac` at this try. Note `mac-runs-on-bare-self-hosted` says why a bare label is wrong.

## The expression is not the guard against fork code

A fork's pull request runs the fork's own copy of the workflow file. A fork can name the Mac runner in that copy. The same-repository test does not stop it.

The guard is the repository's Actions setting for fork pull request workflows. It must be `all_external_contributors`, which requires approval for all external contributors. Read by REST at 14:05 CST Nov 25 2026 from `repos/<owner>/claude-settings/actions/permissions/fork-pr-contributor-approval`: `all_external_contributors`. The Mac must not run jobs while that setting is weaker. Debt `fork-actions-setting-unchecked` covers the gap that nothing reads the setting.

This risk existed before this change. The runner was already registered on a public repository.

## Limits

- At 14:05 CST Nov 25 2026 the runner was online and idle. Its labels: `self-hosted`, `macOS`, `ARM64`, `claude-settings-mac`.
- One Mac runs one job at a time.
- A job sent to an offline runner queues. GitHub's time before it gives up is unverified. Clear the variable when the Mac is off.
- The leg is not in `all-jobs-passed` and is not a required check. Under `merge.requiredChecks` "first-proof", which main pins (decision `merge-needs-current-base`), the lane lint reads no draft run. So a queued leg blocks no merge.
- The Mac may lack Python 3.15, node and npm. Not checked.
- Code from a same-repository pull request runs on the Mac as the guest account. Its files persist across jobs. Debt `mac-runner-state-persists` covers this.

## Notes

- A bare `self-hosted` value matches every self-hosted runner. Note `mac-runs-on-bare-self-hosted`.
- The job name `run (macos-latest)` hides that the Mac ran the job. Note `mac-job-name-hides-runner`.

## Retire

This try ends when the owner's larger plan lands: a clean guest account, or an ephemeral runner for each job. Debts `mac-runner-state-persists` and `fork-actions-setting-unchecked` name their own retirements.

Kind: process
Home: .github/workflows/lane-touched-tests.yml
