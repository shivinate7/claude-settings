---
name: ci-hygiene
description: Use when a session creates or edits CI config (GitHub Actions, workflow files, .github/workflows, other CI files), or when the user says CI is slow, queued, or flaky, or says "ci-hygiene". Not for ordinary code edits. Keeps CI fast, cheap, and trusted.
---

Written for GitHub Actions. The same ideas apply to other CI systems. Commands and YAML are in
`snippets.md` in this skill folder. Read it when you write the config.

## Procedure

1. **Measure first.** Rank the step times of a finished run. Optimize the slowest step only.
   Never guess which step is slow. Measure wall time on the slowest job, not runner minutes
   alone: a cut off a job that is not the slowest saves money, not waiting. Also read the billed
   minutes each week, and set a spending alarm in the billing settings. See `snippets.md`.
2. **Check what exists.** Read the current workflow and the log before you build a speedup. The
   step may already run in parallel, or be cached.
3. **Gate slow checks on their inputs.** Run a slow check after a change to the files it reads.
   Detect the change with `git diff` against the base commit. Add a nightly full run and a manual
   trigger. If detection cannot read the diff, run the check (fail safe). A check that cannot
   read its own input exits non-zero in CI, never 0: CI reads an exit code as a verdict.
4. **Cancel superseded runs.** Set `concurrency` with `cancel-in-progress`, so a new push to a
   ref cancels the old run on that ref. Never cancel a run on the default branch: each merge
   needs its own verdict. Runners with a low concurrency cap, such as hosted
   macOS, queue first.
5. **Cap each job's time.** Set `timeout-minutes` on each job at about 2x its slowest green run.
   Give a network step, such as a browser install, its own short cap.
6. **After a merge, read every run the push starts.** A deploy or nightly workflow is not a
   required check, so its failure shows on no PR.
7. **Pin and audit actions.** Pin each third-party action by full commit SHA, with the version as
   a comment. Let a bot keep the pins current. Disable credential persistence on checkout. Run
   an audit tool in CI, and run it locally with the exact CI command and paths.
   If the installed tool's `--version` matches the CI pin, use it. If it does not, install a copy.
8. **Batch green PRs.** Merge PRs that are green together through one integration branch. One CI
   run then covers the combined code. "No conflicts" does not prove they work together. Green CI
   does not prove that no line was lost either: run `lint/check_silent_undo.py` before the merge.
   GitHub's merge queue needs an organization-owned repo, so a personal repo batches by hand or
   through the merge tool.
   Batch across sessions too. Before a PR runs CI, list the repo's open PRs. When another session's
   PR will be ready at about the same time, offer one integration branch. A repo may name one merge
   steward session. That session owns all merges into main.
9. **Wait without loops.** Watch a run once, in the background, and keep its output. Never poll
   with a sleep loop.
10. **Prove each new gate red once.** Break the gate's target on a scratch copy. Watch the gate
   fail. Restore the target. A gate you did not see go red is not proven.
11. **No CI on a draft.** Run the PR workflow on `opened`, `synchronize`, `reopened` and
    `ready_for_review`, and skip each job while the PR is a draft. Work in a draft. Mark it ready
    once. A draft cannot merge, so it needs no check yet. Read the protection rules first: see
    "Before you skip a required job". A fan-in job with `if: always()` needs its own draft guard.
    A workflow that also has `on: push` for all branches still runs on a draft branch.
12. **Cheap checks first.** Give each expensive job `needs:` the cheap static job. A red static
    check then stops the shards from starting.
13. **Merge tiny jobs.** Each job bills whole minutes, rounded up, plus its own setup. Put checks
    under about a minute into one job. This saves money in private repos only: standard hosted
    runners are free in public repos. Measure billed minutes and wall time before and after.
    Merged jobs can make the wait longer. Per-job rounding is measured, not a documented rule.
14. **Cache the install.** Cache the package install, for example `actions/setup-node` with
    `cache: npm`. Measure the step before and after.
15. **Split the slowest job in a public repo.** Step 13 does not help there. Split the slowest
    serial job into parallel jobs instead. Measured: the longest Windows job went from about
    20 min to 8m59s (PR 289), with no coverage lost.
16. **Pin every suite in a split-job guard.** A guard that checks a split job's suite list must
    also pin each suite's `if:`, `shell:` and `!cancelled()`. It must fail on a job-level `if:` or
    env override. A list-only guard stayed green with a suite turned off (review of PR 289;
    `MERGE_TESTS` at job level, review of PR 293).
17. **Slice tests on a slow platform.** On PRs, run a platform-specific test slice. Run the full
    suite on main and nightly. Measured: the Windows merge job went from 8m59s to 1m13s (PR 293).
18. **Profile before you refactor test setup.** Compare setup time to test-body time. If
    the saving is under 20%, stop. Measured: setup was 31% of the time, and setup reuse saved about 9%
    (decision ci-wall-time-cuts, cut D).

## Before you skip a required job

Branch protection decides if a skipped job counts as passing. Read the protection rules first.
See `snippets.md`.

## Docs

CI claims in README or docs go stale too. See the `fresh-prose` skill.

## Opt-in templates

Adopt each by `uses: shivinate7/claude-settings/actions/<name>@<full-sha>`, or copy the file.
Record: `decisions/opt-in-ci-templates-composite.md`. Steps 1 and 11 to 14: `decisions/ci-spend-rules.md`.

- `all-jobs-passed`: in a job with `needs: [...]` and `if: always()`, pass `toJSON(needs)` as shown. A skipped needed job then fails.

  ```yaml
  with:
    needs: ${{ toJSON(needs) }}
  ```
- `ci-alarm`: in a nightly workflow with `permissions: {actions: read, issues: write}`. One issue opens when main's latest run is red.
- `readme-links`: in a weekly workflow after checkout, never per PR. Set `open-issue: true` with `issues: write`.
- `githooks/main-ref`: run `sh githooks/main-ref/install.sh` in each clone. It refuses a local move of main to a commit origin lacks.
- `testing/skip-locally-fail-in-ci.mjs`: wrap an env-dependent probe in `needEnv`. It skips locally and fails when `CI` is set.
