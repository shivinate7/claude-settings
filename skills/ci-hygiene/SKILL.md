---
name: ci-hygiene
description: Use when a session creates or edits CI config (GitHub Actions, workflow files, .github/workflows, other CI files), or when the user says CI is slow, queued, or flaky, or says "ci-hygiene". Not for ordinary code edits. Keeps CI fast, cheap, and trusted.
---

Written for GitHub Actions. The same ideas apply to other CI systems. Commands and YAML are in
`snippets.md` in this skill folder. Read it when you write the config.

## Procedure

0. **Read the visibility first.** Run `gh repo view --json visibility`. See `snippets.md`,
   section 11. Note which steps apply. Steps tagged **(private repos)** save billed minutes only.
   The **Public repos** section applies to a public repo. An internal repo counts as private.
1. **Measure first.** Rank the CI step times of a finished run. Optimize the slowest CI step only.
   Never guess which CI step is slow. Measure wall time on the slowest job, not runner minutes
   alone: a cut off a job that is not the slowest saves money, not waiting. **(private repos)**
   Also read the billed minutes each week, and set a spending alarm in the billing settings.
   See `snippets.md`.
   Time the before and the after back to back, under the same machine load. Note the load
   beside each time: CPU use, and what else ran. A time taken under load does not compare with
   one taken on a quiet machine.
2. **Check what exists.** Read the current workflow and the log before you build a speedup. The
   CI step may already run in parallel, or be cached.
3. **Gate slow checks on their inputs.** Run a slow check after a change to the files it reads.
   Detect the change with `git diff` against the base commit. Add a nightly full run and a manual
   trigger. If detection cannot read the diff, run the check (fail safe). A check that cannot
   read its own input exits non-zero in CI, never 0: CI reads an exit code as a verdict.
4. **Cancel superseded runs.** Set `concurrency` with `cancel-in-progress`, so a new push to a
   ref cancels the old run on that ref. Never cancel a run on the default branch: each merge
   needs its own verdict. `cancel-in-progress: false` is not enough: a group keeps one pending
   run and a newer one replaces it. Give each default-branch run its own group. Put the PR draft
   state in the group (`format('{0}-{1}', github.ref, github.event.pull_request.draft)`). A draft
   run skips every job (step 11), so it must never cancel a ready run. Runners with a low
   concurrency cap, such as hosted macOS, queue first.
5. **Cap each job's time.** A job with fewer than 5 green runs takes a provisional cap of 60
   minutes, marked `# provisional` in a comment. The owner may set another provisional cap.
   After 5 green runs, set the cap at about 2x the slowest, from measured times. Keep
   `merge.deadlineMinutes` in `.github/stamp.json` at least the largest cap plus 5. The merge
   tool warns when a job passes 70% of its cap. A timeout stays red, labelled "re-cap or split".
   Give a network step, such as a browser install, its own short cap.
   When a job nears its cap, split the slowest suite's subject by family into its own job. Give
   the measured CI time before and after.
6. **After a merge, read every run the push starts.** A deploy or nightly workflow is not a
   required check, so its failure shows on no PR.
7. **Pin and audit actions.** Pin each third-party action by full commit SHA, with the version as
   a comment. Name the bot that keeps each pin current. Here, `.github/dependabot.yml` ignores
   all version updates for actions. Renovate tracks three custom pins, not actions
   (`renovate.json`). Disable credential persistence on checkout. Run an
   audit tool in CI, and run the same command locally: see the zizmor step in
   `.github/workflows/gates.yml`.
8. **Batch lanes.** One CI run per batch, by CLAUDE.md rule `git-integration-branch-merge`.
   "No conflicts" does not prove the lanes work together. A green integration run does not prove
   that no line was lost either: run `lint/check_silent_undo.py` before the merge.
   GitHub's merge queue needs an organization-owned repo, so a personal repo batches by hand or
   through the merge tool.
   Batch across sessions too. Before a PR runs CI, list the repo's open PRs. When another session's
   lane passes its local checks at about the same time, offer one integration branch. A repo may
   name one session to batch PRs and run each merge, on the owner's grant.
9. **Wait without loops.** Wait for the CI-wake notice that follows `gh pr ready`. A push
   starts no notice. Never run `gh run watch`: one watch made 131 API calls a minute (decision
   ci-wait-reads-run-status, CI waits read the run status). Never poll with a sleep loop. A repeated `gh run view` or
   `gh pr checks` without `--watch` is a poll. To wait for any other condition, use the Monitor
   tool (decision agents-wait-with-monitor, agents wait with the Monitor tool). See `snippets.md`.
10. **Prove each new gate red once.** Break the gate's target on a scratch copy. Watch the gate
   fail. Restore the target. A gate you did not see go red is not proven.
   A pipe hides a gate's exit code. `lint | tail -1` exits 0 when lint fails, so a commit after
   it runs on a red gate. Gate on the command's own exit code. See `snippets.md`, section 10.
11. **No CI on a draft.** Run the PR workflow on `opened`, `synchronize`, `reopened` and
    `ready_for_review`. Skip every job while the PR is a draft, the required check included. Work
    in a draft. Only the integration PR goes ready, once (step 8). A draft cannot merge, so it
    needs no check yet. Read the protection rules first: see
    "Before you skip a required job". A fan-in job with `if: always()` needs its own draft guard.
    A workflow that also has `on: push` for all branches still runs on a draft branch.
    `gh pr create --draft` then `gh pr ready` fires two runs: keep the draft state in the
    `concurrency` group (step 4), or the skipped draft run cancels an in-progress ready run.
    Run `gh pr ready` only after the draft run shows in `gh run list`. A ready sent seconds
    after the PR opens can give both runs `draft=false`. One then cancels the other, and
    its cancelled check runs can block the merge, even for an admin (PR 381, Sonnet prompt judges).
    After `gh pr ready`, a run of only skipped jobs proves nothing. Wait for a run on the head
    that ran, or dispatch one. See `snippets.md`, section 5b. Never mark ready in the same second
    as the create. (The merge tool refuses an all-skipped head. Incidents: PR 352, per-file
    checkout in a worktree, and PR 360, rm rules beside a redirect.)
12. **Cheap checks first.** Give each expensive job `needs:` the cheap static job. A red static
    check then stops the shards from starting.
13. **Merge tiny jobs (private repos).** Each job bills whole minutes, rounded up, plus its own setup. Put checks
    under about a minute into one job. This saves money in private repos only: standard hosted
    runners are free in public repos. Measure billed minutes and wall time before and after.
    Merged jobs can make the wait longer. Per-job rounding is measured, not a documented rule.
    For wall time, see step 15.
14. **Cache the install.** Cache the package install, for example `actions/setup-node` with
    `cache: npm`. Measure the step before and after.
15. **Split the slowest job for wall time.** Use it where minutes are free, as in a
    public repo. Step 13 saves money, not time. Split the slowest serial job into parallel jobs.
    `lint/test_windows_split.py` checks that each suite runs in exactly one job. In the CI run 37675874835 (2026-10-07) of PR 293, the Windows merge-test slice, the longest
    Windows job took 6m24s.
16. **Pin every suite in a split-job guard.** The guard must pin each suite's `if:`, `shell:` and
    `!cancelled()`, with no env override (`MERGE_TESTS` gap, review of PR 293, the Windows merge-test slice). A job-level `if:`
    names only its own scope flag, or a non-PR event (step 19).
17. **Slice tests on a slow platform.** On PRs, run a platform-specific test slice. Run the full
    suite on main and nightly. Measured: the Windows merge slice took 1m13s in CI run
    37675874835 of PR 293.
18. **Profile before you refactor test setup.** Compare setup time to test-body time. If
    the saving is under 20%, stop. Measured: setup was 31% of the time, and setup reuse saved
    about 9% (merge test setup).
19. **Run one scope job first.** Make it a cheap Linux job. Give every other job `needs: scope`.
    Most jobs add a job-level `if:` on their own flag. That `if:` also holds
    `|| github.event_name != 'pull_request'`, so push, nightly and dispatch runs start them.
    The `gates` job has no job-level `if:`. Its steps carry the flags.
    Two jobs may share a flag: this repo's `gates-mutate-guard` and `gates-windows-guard` both
    read `guard`. A job with nothing to test then starts no runner. A docs-only PR skips the code
    suites. `gates` still runs its lint steps. An unreadable diff or an unmapped path runs everything. A skipped job
    reads as passing. Put the scope job in the required checks.

## Public repos

Fork PRs run code you did not write. Apply these to a public repo. See `snippets.md`, section 11.

- Never expose secrets to a fork's run. A fork's `pull_request` run gets no secrets, and its
  `GITHUB_TOKEN` is read-only.
- Avoid `pull_request_target` with a checkout of the PR's head. That trigger runs the default
  branch with secrets and write access.
- Pin every third-party action by full SHA. Step 7 applies in full, and matters more here.
- Give workflows least-privilege `permissions`. Default the token to read-only at the top level.
  If a job needs more, restate `contents: read` in that job's block with the extra scope. A
  `permissions` block sets every scope it does not name to `none`.
- Keep one CI run per batch (step 8). Free minutes do not remove queue time, and each run
  costs `gh` calls on the shared token.

## Before you skip a required job

Branch protection decides if a skipped job counts as passing. Read the protection rules first.
See `snippets.md`.

The required check names are a copy of `merge.requiredChecks` in `.github/stamp.json`. A rename
edits both. A PUT on the protection API replaces the whole rule, so it drops any field you leave
out. (Decision main-branch-protection: the required checks on main.)

## Docs

CI claims in README or docs go stale too. See the `fresh-prose` skill.

## Opt-in templates

Adopt each by `uses: shivinate7/claude-settings/actions/<name>@<full-sha>`, or copy the file.
Record: decision opt-in-ci-templates-composite (opt-in CI templates are composite actions).

- `all-jobs-passed`: in a job with `needs: [...]` and `if: always()`, pass `toJSON(needs)` as shown. A skipped needed job then fails.

  ```yaml
  with:
    needs: ${{ toJSON(needs) }}
  ```
- `ci-alarm`: in a nightly workflow with `permissions: {actions: read, issues: write}`. One issue opens when main's latest run is red.
- `readme-links`: in a weekly workflow after checkout, never per PR. Set `open-issue: true` with `issues: write`.
- `ruling-kind`: in a pull_request job after `actions/checkout` with `fetch-depth: 0`. It fails when a changed `decisions/*.md` record has no valid Kind line, or when the base cannot be read.
- `githooks/main-ref`: run `sh githooks/main-ref/install.sh` in each clone. It refuses a local move of main to a commit origin lacks.
- `testing/skip-locally-fail-in-ci.mjs`: wrap an env-dependent probe in `needEnv`. It skips locally and fails when `CI` is set.
