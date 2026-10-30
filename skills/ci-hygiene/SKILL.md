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
   alone. A cut to a job that is not the slowest saves money, not waiting. **(private repos)**
   Also read the billed minutes each week. Set a spending alarm in the billing settings. See
   `snippets.md`, section 1.
   Time the before and the after back to back, under the same machine load. Note the load beside
   each time: CPU use, and what else ran. A time taken under load does not compare with one taken
   on a quiet machine.
2. **Check what exists.** Read the current workflow and the log before you build a speedup. The
   CI step may already run in parallel, or be cached.
3. **Run slow checks only on their inputs.** Run a slow check after a change to the files it reads.
   Detect the change with `git diff` against the base commit. Add a nightly full run and a manual
   trigger. If detection cannot read the diff, run the check. That fails safe. A check that cannot
   read its own input exits non-zero in CI, never 0. CI reads the exit code as the verdict (decision
   `ci-unknown-is-red`, an unknown read is red in CI).
4. **Cancel superseded runs.** Set `concurrency` with `cancel-in-progress`. A new push to a ref then
   cancels the old run on that ref. Never cancel a run on the default branch. Each merge needs its
   own verdict. `cancel-in-progress: false` is not enough. A group keeps one pending run, and a newer
   run replaces it. Give each default-branch run its own group. Put the PR draft state in the group,
   as `snippets.md`, section 4 shows. A draft run skips every job (step 11), so it must never cancel
   a ready run. Runners with a low concurrency cap, such as hosted macOS, queue first.
5. **Cap each job's time.** A new job takes a provisional cap of 60 minutes until it has 5 green
   runs. Mark the cap `# provisional` in a comment. The owner may set another provisional cap. After
   5 green runs, set the cap at about 2x the slowest of the newest 30 completed runs. Decision
   `ci-job-caps` (each job's cap) holds the table, the target (a slowest run under 80% of the cap)
   and how to measure again. Keep `merge.deadlineMinutes` in `.github/stamp.json` at least the
   largest cap plus 5. The merge tool warns at 70% of a cap. A job that ends at
   its cap with no red CI step is re-capped or split. It is never left. A timeout stays red,
   labelled "re-cap or split". Give a network step, such as a browser install, its own short cap.
   When a job nears its cap, split its slowest suite by family into its own job. Give the measured
   CI time before and after. Decision `test-strategy-reset` (each suite in one job) holds that split.
6. **After a merge, read every run the push starts.** A deploy or nightly workflow is not a required
   check. So its failure shows on no PR. See `snippets.md`, section 6.
7. **Pin and audit actions.** Pin each third-party action by full commit SHA. Put its version in a
   comment. Set `persist-credentials: false` on each checkout. Run an audit tool in CI, and run the
   same command locally. See `snippets.md`, section 7, for the zizmor command.
   A pin of claude-settings' `ste-lint` action follows the session's tools. `bin/ste-changed` reads
   that pin. It prints drift and exits 3. The session then moves the pin in a lane of its own. No
   bot and no schedule moves it (decision `action-pins-follow-sessions`). That tool reads only the
   `ste-lint` pin. Other claude-settings pins can drift unseen.
   Other pins keep full-SHA pinning. Which bot, if any, bumps them is set per repo.
8. **Batch lanes.** Batch lanes into one integration branch and one integration PR. The batch runs
   one CI run, by rule `git-integration-branch-merge`. Only the integration PR goes ready. Each lane
   PR stays a draft until the integration PR merges. A lane runs `bin/ci-job checks --lint --base
   origin/main` before it joins. A lane never runs a whole CI job (decision `lanes-run-no-full-ci-job`).
   Never push to a ready PR while its CI run can still go green. A late lane joins the next batch.
   Once a job is red, push the lane drop or the lane fix at once. The push cancels the old run.
   Never make an empty commit, or close and reopen a PR, to restart CI.
   No merge to main while a batch's run is in progress. That binds the owner too (decision
   `no-merge-during-batch-ci`). A merge needs a green run on the current base. A head that lacks the
   base tip is refused, except a small move (decision `merge-needs-current-base`).
   "No conflicts" does not prove the lanes work together. A green integration run does not prove that
   no line was lost either. Run `lint/check_silent_undo.py` before the merge.
   GitHub's merge queue needs an organization-owned repo. A personal repo batches by hand or through
   the merge tool.
   Batch across sessions too. Before you open a PR, list the repo's open PRs. When another session's
   lane passes its local checks at about the same time, offer one integration branch. A repo may
   name one session to batch PRs and run each merge, on the owner's grant.
9. **Wait without loops.** Wait for the CI-wake notice that follows `gh pr ready`. A push starts no
   notice. Never run `gh run watch`. One watch made 131 API calls in one minute (decision
   `ci-wait-reads-run-status`, CI waits read the run status). Never poll with a sleep loop. Repeated
   `gh run view` or `gh pr checks` calls are a poll. To wait for any other condition, use the
   Monitor tool (decision `agents-wait-with-monitor`). See `snippets.md`, section 9.
   A cloud session waits on its PR subscription. At the start of a wait, it sets a `send_later`
   check-in. It sets another after each red job, each wider apart. A run with a red job sends no "all checks
   done" wake (rule `git-ci-wait-checks-in`). A red run posts one PR comment from its last job, the
   `ci-done-comment` template. That comment wakes the session that watches the PR (rule
   `git-ci-done-comment-wakes`).
10. **Prove each new check red once.** Break the check's target on a scratch copy. Watch the check
    fail. Restore the target. A check you did not see go red is not proven. A pipe hides a check's
    exit code. `lint | tail -1` exits 0 when lint fails. So a commit after it runs on a red check.
    Decide on the command's own exit code. See `snippets.md`, section 10.
11. **No CI on a draft.** Run the PR workflow on `opened`, `synchronize`, `reopened` and
    `ready_for_review`. Skip every job while the PR is a draft. The rollup job skips too. Read
    "Before you skip a required job". Decision `draft-until-reviewed` holds the rule. A draft cannot
    merge, so it needs no check. Only the integration PR goes ready, once (step 8).
    A workflow that also has `on: push` for all branches still runs on a draft branch.
    `gh pr create --draft` then `gh pr ready` fires two runs. Keep the draft state in the concurrency
    group (step 4). Otherwise the skipped draft run cancels an in-progress ready run.
    Run `gh pr ready` only after the draft run shows in `gh run list`. A ready sent seconds after the
    PR opens can give both runs `draft=false`. One then cancels the other. Its cancelled check runs
    can stop the merge, even for an admin (PR 381, Sonnet prompt judges).
    After `gh pr ready`, a run of only skipped jobs proves nothing. Wait for a run on the head that
    ran, or dispatch one. See `snippets.md`, section 5b. Never mark ready in the same second as the
    create. The merge tool refuses an all-skipped head. Incidents: PR 352 (per-file checkout in a
    worktree) and PR 360 (rm rules beside a redirect).
12. **Cheap checks first.** Give each expensive job `needs:` the cheap static job. A red static check
    then stops the shards from starting.
13. **Merge tiny jobs (private repos).** Each job bills whole minutes, rounded up, plus its own setup.
    Put checks under about a minute into one job. This saves money in private repos only. Standard
    hosted runners are free in public repos. Measure billed minutes and wall time before and after.
    Merged jobs can make the wait longer. Per-job rounding is measured, not a documented rule. For
    wall time, see step 15.
14. **Cache the install.** Cache the package install. For example, `actions/setup-node` with
    `cache: npm`. Measure the CI step before and after.
15. **Split the slowest job for wall time.** Use it where minutes are free, as in a public repo.
    Step 13 saves money, not time. Split the slowest serial job into parallel jobs.
    `lint/test_windows_split.py` checks that each suite runs in exactly one job. In this repo, the
    longest Windows job took 6m24s in CI run 37675874835 (2026-10-07) of PR 293, the Windows
    merge-test slice.
16. **Pin every suite in a split-job guard.** The guard must pin each suite's CI step `if:`,
    `shell:` and `!cancelled()`, with no env override. The `MERGE_TESTS` gap, found in review of
    PR 293 (the Windows merge-test slice), is the case for it. A CI step's `if:` names only its own
    scope flag, or a non-PR event (step 19).
17. **Slice tests on a slow platform.** On PRs, run a platform-specific test slice. Run the full suite
    on main and nightly. In this repo, the Windows merge slice took 1m13s in CI run 37675874835 of
    PR 293.
18. **Profile before you refactor test setup.** Compare setup time to test-body time. If the saving is
    under 20%, stop. In this repo, setup was 31% of the time, and setup reuse saved about 9% (merge
    test setup).
19. **Run one scope job first.** Make it a cheap Linux job named `scope`. Every other job needs it.
    A scope skip sits on the CI step that runs the suite or lint, never on the job. A job-level `if:`
    holds only the draft guard. A job that runs only off pull requests, such as a push-only job, also
    skips at its CI steps. A skipped job fails the rollup on every PR. Each scoped CI step's `if:`
    names its scope flag and `|| github.event_name != 'pull_request'`, so push, nightly and dispatch
    runs start it. See `snippets.md`, section 19.
    A job whose CI steps all skip still starts a runner. It bills its setup minutes (step 13).
    Unmeasured: the size of that cost in this repo. This rule for trigger guards goes beyond decision
    `same-check-kinds`, which names scope flags only.
    Two jobs may share a flag. In this repo, `checks-mutate-guard` and `checks-windows-guard` both
    read `guard`. A docs-only PR skips the code suites. `checks` still runs its lint CI steps. An
    unreadable diff or an unmapped path runs everything. In this repo, `checks` has no job-level
    `if:`. Its CI steps carry the flags.

## Public repos

Fork PRs run code you did not write. Apply these to a public repo. See `snippets.md`, section 11.

- Never expose secrets to a fork's run. A fork's `pull_request` run gets no secrets. Its
  `GITHUB_TOKEN` is read-only.
- Avoid `pull_request_target` with a checkout of the PR's head. That trigger runs the default
  branch with secrets and write access.
- Pin every third-party action by full SHA. Step 7 applies in full, and matters more here.
- Give workflows least-privilege `permissions`. Default the token to read-only at the top level.
  If a job needs more, restate `contents: read` in that job's block with the extra scope. A
  `permissions` block sets every scope it does not name to `none`.
- Keep one CI run per batch (step 8). Free minutes do not remove queue time. Each run costs `gh`
  calls on the shared token.

## Before you skip a required job

Branch protection decides what counts as passing. Every repo runs the same kinds of checks, judged by
the same outcomes (decision `same-check-kinds`). Branch protection requires one check: the
`all-jobs-passed` rollup. That job lists every other job in `needs:`, and its `if:` holds `always()`.
The rollup fails a needed job that failed, was cancelled or was skipped. Without the rollup, a
skipped job reads as passing. So a scoped-out suite skips at its CI step, and its job still runs and
passes. The rollup skips on a draft, and a draft cannot merge (step 11). Read the protection rule
first: `snippets.md`, section 3b.

This repo's CI has no `all-jobs-passed` job yet. Its branch protection is not read here. So its
required checks are unmeasured.

The required check names live in the branch protection. `merge.requiredChecks` in
`.github/stamp.json` says `"protection"`, so `merge` reads them from there. A repo that pins a list
in `stamp.json` instead must keep it equal to the protection. `merge` refuses a disagreement. A
rename edits the protection. A PUT on the protection API replaces the whole rule. It drops any field
you leave out (decision `main-branch-protection`, the required checks on main).

## Docs

CI claims in README or docs go stale too. See the `fresh-prose` skill.

## Opt-in templates

Each template is one home: a composite action under `actions/<name>/`, or a plain file (decision
`opt-in-ci-templates-composite`). Adopt an action with
`uses: shivinate7/claude-settings/actions/<name>@<full-sha>`, or copy the file. Each line below
gives the action's purpose from its `action.yml`.

The seven opt-in templates of that decision:

- `all-jobs-passed`: fan-in check. Fails when a needed job failed, was cancelled or was skipped. The
  caller job sets `needs: [...]` and `if: always()`, and passes `with: needs: ${{ toJSON(needs) }}`.
- `ci-done-comment`: posts one PR comment when a run ends with a failed or cancelled job. The caller
  is the last job. It sets `needs:` on every other job, and
  `if: ${{ !cancelled() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}`.
  It also sets `permissions: {pull-requests: write}` and `with: needs: ${{ toJSON(needs) }}`.
- `ci-alarm`: opens or comments on one issue when the latest completed run of any workflow on a
  branch (default `main`) is red. The caller is a scheduled workflow with
  `permissions: {actions: read, issues: write}`. It needs no checkout. The nightly alarm is not
  enabled in this repo.
- `readme-links`: checks the external https links in a markdown file (default `README.md`). Run it
  from a weekly schedule, never per PR. With `open-issue: true`, a dead link opens or updates one
  issue (`issues: write`). The caller needs checkout.
- `ruling-kind`: fails a PR that adds or edits a record in the records folder with no valid Kind line.
  The caller is a pull_request job with checkout at `fetch-depth: 0`. It fails closed when the base
  cannot be read.
- `githooks/main-ref`: refuses a local move of main to a commit that origin lacks. Run
  `sh githooks/main-ref/install.sh` in each clone.
- `testing/skip-locally-fail-in-ci.mjs`: wrap an env-dependent probe in `needEnv`. It skips locally.
  It fails when `CI` is set.

The other composite actions in `actions/`, in the same home:

- `code-check`: one type check and one lint for defects per language, from `standard.json`. Fails on
  a tracked language with no row, on a defect a pinned tool finds, and on a mypy list that shrank
  against the base or the default branch. The caller needs checkout at `fetch-depth: 0` and
  setup-python.
- `playwright-setup`: installs the Playwright that a lockfile pins, and its browsers. No apt step by
  default. Opt-in `system-deps` installs webkit or firefox libraries on Linux, under a 300 s cap.
- `ste-lint`: runs `lint/ste_lint.py` on changed Markdown (default) or on every file (`scope: all`).
  Fails on added or changed lines only. The caller needs checkout at `fetch-depth: 0`.
- `stamp`: runs `stamp.mjs --check` on the records. A pending record on the default branch fails it.
  The caller owns the config file.
- `all-jobs-passed`, `ci-done-comment`, `ci-alarm`, `readme-links` and `ruling-kind` are listed above.

## Audit a repo

Run these checks against `.github/workflows/*.yml` and the branch protection. Answer yes or no. A no
is a finding. A read that cannot run is unknown, never yes or no (rule `verification-report-unknown-reads`).

1. Does a job named `all-jobs-passed` exist? Read `.github/workflows/*.yml`.
2. Does that job list every other job in `needs:`, except `ci-done`, with `if:` holding `always()` and
   the draft guard? Read its job block.
3. Does branch protection require exactly one check, `all-jobs-passed`? Read
   `gh api repos/<owner>/<repo>/branches/main/protection`. A 403 is unknown.
4. Do the PR triggers include `opened`, `synchronize`, `reopened` and `ready_for_review`? Read each
   `on: pull_request: types:` line.
5. Does every job skip on a draft, directly or through `needs:`? Read each job's `if:` and `needs:`.
6. Does the top-level `concurrency:` group hold the PR draft state, and never cancel a default-branch
   run? Read the block. Compare it with `snippets.md`, section 4.
7. Does every job set `timeout-minutes`? Run `grep -n "timeout-minutes" .github/workflows/*.yml`
   and compare the count with the job list from `grep -n "^  [a-z]" .github/workflows/*.yml`.
8. Is every `uses:` pinned by a full 40-character SHA, except same-repo `$/` and `./` actions? Run
   `grep -n "uses:" .github/workflows/*.yml` and read each line.
9. Does every `actions/checkout` set `persist-credentials: false`? Run
   `grep -n -A3 "actions/checkout" .github/workflows/*.yml`.
10. Is the top-level `permissions:` read-only, with `contents: read` or narrower? Read the lines above
    `jobs:` in each workflow.
11. Is there no `pull_request_target` that checks out the PR head? Run
    `grep -n "pull_request_target" .github/workflows/*.yml`. For each hit, read its `ref:`.
12. Does every job-level `if:` hold only the draft guard, or the guard of `ci-done`? Run
    `grep -n "^    if:" .github/workflows/*.yml`. A scope flag or a trigger guard at job level is a
    finding. It skips a needed job.
13. Is the last job `ci-done`, with `needs:` every other job and a call to `ci-done-comment`? Read the
    last job block.
14. Does no `run:` pipe a check into `tail` or `head` without `set -o pipefail`? Run
    `grep -nE "\| *(tail|head)" .github/workflows/*.yml`, then read each hit.
15. Does an audit step run in CI and locally, with a pinned version? Run
    `grep -n "zizmor" .github/workflows/*.yml`. Read the version pin.
