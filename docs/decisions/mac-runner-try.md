---
id: pending
slug: mac-runner-try
---

# The macOS leg may run on the owner's self-hosted Mac, as a try

## The ruling

Owner, 13:18 CST Nov 25 2026, typed in the consultant's chat. His self-hosted Mac runner is its own guest account on his Mac, not his main account. It is not always on. He wrote: "feel free to give it a shot if it seems faster sure use it for now and if not then don't". He also wrote: "we can carve out a larger plan on it when i'm back for now im allowing u to freestyle it on the runner".

The try: the macOS leg of `lane-touched-tests.yml` (the `run` job) may run on that Mac. The repository variable `MAC_RUNS_ON` is the switch. This decision holds the question of where the macOS leg runs. Decision `draft-until-reviewed` holds the draft gate and the leg's file selection, and points here.

## What the workflow does

- The `run` job's `runs-on` reads `MAC_RUNS_ON` for a same-repository pull request. The macOS leg runs on the label that the variable holds.
- Unset or empty means hosted: the macOS leg runs on `macos-latest`.
- The Windows leg never reads the variable. The `touched` job runs on Linux.
- Before `On`, read the Actions setting that guards fork pull requests: `gh api repos/shivinate7/claude-settings/actions/permissions/fork-pr-contributor-approval`. Expect `all_external_contributors`.
- On: `gh variable set MAC_RUNS_ON --body <label>`. Off: `gh variable delete MAC_RUNS_ON`.
- Set the value to the runner's own label, which is `claude-settings-mac`. Note `mac-runs-on-bare-self-hosted` says why a bare label is wrong.
- Before a maintainer lets a held fork run go, read the fork's workflow diff. That run goes to the Mac if the fork's copy names it.

## The expression is not the guard against fork code

A fork's pull request runs the fork's own copy of the workflow file. A fork can name the Mac runner in that copy. The same-repository test does not stop it.

The guard is the repository's Actions setting for fork pull request workflows. It must be `all_external_contributors`, which requires approval for all external contributors. Read by REST at 14:05 CST Nov 25 2026 from `repos/<owner>/claude-settings/actions/permissions/fork-pr-contributor-approval`: `all_external_contributors`. The Mac must not run jobs while that setting is weaker. Debt `fork-actions-setting-unchecked` covers the gap that nothing reads the setting.

This risk existed before this change. The runner was already registered on a public repository.

## Limits

- At 14:05 CST Nov 25 2026 the runner was online and idle. Its labels: `self-hosted`, `macOS`, `ARM64`, `claude-settings-mac`.
- One Mac runs one job at a time.
- A job sent to an offline runner queues. GitHub's time before it gives up is unverified. Clear the variable when the Mac is off.
- The leg is not in `all-jobs-passed` and is not a required check. Under `merge.requiredChecks` "first-proof", which main pins (decision `merge-needs-current-base`), the lane lint reads no draft run, and the merge tool's confirm drops a pending run of a workflow with no required job (`required_only`, merge/merge.py). So a queued leg blocks no lane lint and no confirm.
- The guard's head check, `head_read` in merge/merge.py (wrapped by `merge_check` in hooks/guard_merge.py, refused in hooks/guard.py), counts any unfinished run as pending. So a merge outside the merge tool, a raw `gh pr merge` or the GitHub MCP merge, is refused while the leg is queued. Remedy: the merge tool.
- A red leg blocks the merge tool on that head. The merge tool reads it as red (`head_state`), and a lane-lint PASS lifts only pending. The guard refuses it too. It clears on a push, or when a newer run of the same workflow passes (the newest run per name counts; the GitHub re-run path is unverified).
- The Mac may lack Python 3.15, node and npm. Not checked.
- Code from a same-repository pull request runs on the Mac as the guest account. Its files persist across jobs. Debt `mac-runner-state-persists` covers this.

## Notes

- A bare `self-hosted` value matches every self-hosted runner. Note `mac-runs-on-bare-self-hosted`.
- The job name `run (macos-latest)` hides that the Mac ran the job. Note `mac-job-name-hides-runner`.

## Retire

The try stops when the Mac does not seem faster. The owner's words: "if not then don't". It ends for good when the owner's larger plan lands: a clean account, or an ephemeral runner for each job. Debts `mac-runner-state-persists` and `fork-actions-setting-unchecked` name their own retirements.

Kind: process
Home: .github/workflows/lane-touched-tests.yml
