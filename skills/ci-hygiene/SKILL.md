---
name: ci-hygiene
description: Use when a session creates or edits CI config (GitHub Actions, workflow files, .github/workflows, other CI files), or when the user says CI is slow, queued, or flaky, or says "ci-hygiene", or when a session batches lane PRs into one integration branch, or a batch's integration run is red. Not for ordinary code edits. Keeps CI fast, cheap, and trusted.
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
5. **Cap each job's time.** Caps are generous on purpose, as a stopgap, until the repo's
   time-pinned tests are gone. Decision `ci-job-caps` (each job's cap)
   holds the rule, the table and how to measure again. A new job's provisional cap
   is 60 min. Mark it `# provisional` until it has 5 green runs. The owner may set another
   provisional cap. Keep `merge.deadlineMinutes` in `.github/stamp.json` at least the largest cap
   plus 5. The merge tool's `warn` mode flags a job past 70% of its cap. A job that ends at its cap with no red CI
   step is re-capped or split. It is never left. A timeout stays red, labelled "re-cap or split".
   Give a network step, such as a browser install, its own short cap. When a job nears its cap,
   split its slowest suite by family into its own job. Give the measured CI time before and after.
   Decision `test-strategy-reset` (a test must not fail on runner speed) holds that split.
6. **After a merge, read every run the push starts.** A deploy or nightly workflow is not a required
   check. So its failure shows on no PR. See `snippets.md`, section 6.
7. **Pin and audit actions.** Pin each third-party action by full commit SHA. Put its version in a
   comment. Set `persist-credentials: false` on each checkout. Run an audit tool in CI, and run the
   same command locally. See `snippets.md`, section 7, for the zizmor command.
   Pin the audit tool's version too. Read its changelog before a bump (rule
   `verification-newest-that-passes`, take the newest version that passes). zizmor 1.30.0 added the
   `self-repository` audit. It flags each local `uses: ./...` call, an action such as `./actions/a`
   too, not only a workflow. A floating version once turned a PR red.
   Pins of claude-settings' `ste-lint` and `zizmor` actions follow the session's tools (decision
   `action-pins-follow-sessions`). `bin/ste-changed` reads those pins. It prints drift. A direct run exits 3; lane lint shows it as a note. The
   session then moves the pin in a lane of its own. No bot and no schedule moves it. That tool reads
   only the `ste-lint` and `zizmor` pins. Other claude-settings pins can drift unseen.
   Other pins keep full-SHA pinning. Which bot, if any, bumps them is set per repo.
8. **Batch lanes.** The batch rules below stay live until the cutover (decision `all-repos-switch-together`).

   After the cutover (target, not live): each lane PR merges alone through the merge tool, on its own green run and the review its risk needs (rule `git-integration-branch-merge`). Each lane PR goes ready once, after its last review and lane lint (decision `draft-until-reviewed`). After a merge, main's run runs the full suites and the Windows shards (rule `roles-each-layer-proves-once`). A breaking merge is one after which main's newest finished run is red. Its revert PR is an ordinary lane PR, merged with `--base-red-ok` (decision `no-merge-onto-red-main`). After a red main, merges resume when the revert merges, with the revert's own run still going (owner pick 745 b, 2026-11-13 13:20 CST). While main is red, a lane that touches none of the blamed paths may merge (owner pick 746 b; the blame step is not built). Both are target, not live: the built brake still waits for the revert's run on main to be green.

   Until the cutover, batch lanes into one integration branch and one integration PR. A batch runs one
   CI run (rule `git-integration-branch-merge`, one CI run per batch). Only the integration PR goes
   ready. Each lane PR stays a draft until the integration PR merges. A lane runs
   `~/.claude/bin/merge --lane-lint <pr>` before it hands off, and the batch runner runs it again on
   each lane head before the build starts, once per lane. A red lane does not join. Before it marks
   the PR ready, the batch runner runs `~/.claude/bin/merge --lane-lint <PR number>`
   on the head, after the draft step's page push. The ready route (`merge <pr> --ready`) runs the records step and the repo's ready checks (`merge.readyChecks`).
   A lane's `merge --lane-lint <pr> --touched-tests` runs each test file the diff touches, once, in the lint worktree, after the lint passes. That catches a test that fails only on that head before the CI run. A ref target posts no comment, so it cannot
   satisfy the join. A FAIL keeps it a draft. The lint counts a clash between two heads only when both
   merge clean with their base (decision `lanes-run-no-full-ci-job`). A hand list of checks never stands in for that run: `bin/ci-job`
   reads its steps from the workflow, so it cannot miss one. A lane never runs a whole CI job
   (decision `lanes-run-no-full-ci-job`, a lane runs no full CI job).
   **When the build starts, freeze the lane set** (decision `batch-freeze-lane-set`, a batch's lane set
   freezes at its build). A release or a drop that arrives after that goes to the next batch. It never
   triggers a rebuild. The one change after the freeze is the drop of a blamed lane, with any
   lane that depends on it. A lane is blamed when a red run of the batch head names it. Build the batch as a draft,
   run the batch-head lane lint, then mark the integration PR ready, with no rebuild between
   (decision `draft-until-reviewed`). A draft run skips every job, so never rebuild a draft batch
   only to close it. The
   next batch builds and runs on top of the one in CI. While its head holds the running batch's head,
   the running batch may merge (decision `no-merge-during-batch-ci`, the contains rule). A drop
   changes the running batch's head, so the brake refuses that merge until the next batch is built
   on the new head.
   Each lane merges alone: `merge <pr> --confirm --priority-rows <rows file>` takes one PR, with no batch to build, freeze, blame or stack.
   Add `--priority-rows` when the handoff has priority rows, and leave it off when there are no priority rows, because an empty rows file refuses.
   Never push to a ready PR while its CI run can still go green. A late lane joins the next batch.
   Once a job is red, push the lane drop or the lane fix at once. The push cancels the old run, and
   the new run is the re-run. A lone lane is its own integration PR. When the integration PR merges,
   each lane PR closes as replaced.
   When the integration run is red, read the failing job. Find the lane whose files it touches.
   Search one lane merge commit at a time: for each lane merge commit `M` on the integration branch,
   run `git diff --name-only M^1 M` or `git log -1 -m -S<text> M` as its own command, and print the
   lane's name on the line before its hits. Each hit then names exactly one lane. Never run one
   search over the whole range, such as `git log -p -S<text> main..<integration>`, and never run
   two searches in one command: their output joins and the hits blame the wrong lane. A hit in two
   lanes is two names, so read each lane's diff before you drop either. Example: the failing job
   reads `lint/foo.py`. Lane A's own search lists `lint/foo.py` and lane B's lists nothing. Blame A.
   (At 17:10 CST on Nov 8 two searches printed together, so the runner blamed lane B for lane A's
   red.) Then revert the blamed lane's merge as an ordinary PR, merged with `--base-red-ok "<reason>"` (rule `git-red-main-reverts`). A lane whose merge was reverted re-applies its diff after it merges main, and checks that each
   file is there. A job that ends at its cap with no red CI step is re-capped or split. That is not a
   reason to drop the lane.
   A lane that is red on form (record format, version bump, lint) is dropped like any red lane. Its
   fix goes in its own lane, and it joins the next batch.
   A lint red that `bin/ste-changed` passes, while it blames an old `ste-lint` pin, is not a strike
   (decision `action-pins-follow-sessions`, CI pins follow the session's tools). The session moves
   that pin to claude-settings main in a lane of its own, with no question. That lane's reviewer
   checks only that it changes pin lines alone, to a main commit that descends from the old pin.
   Put the fix on the lane branch, never on the integration branch. Run CI again, once, and merge the
   rest. A drop restarts CI at once and re-lints no lane that stays: each lane was linted at hand-off and
   once at the join, before the build, and the batch head once, before ready (decision
   `batch-freeze-lane-set`). Fix the dropped lane in its own lane. It joins the next batch after its fix. A held lane
   (rule `roles-review-cap-three`, three review rounds) is the exception. Drop it and park it. It
   gets no fix lane until the owner decides.
   Until the cutover, no merge to main while a batch's run is in progress. The owner is included. Decision
   `no-merge-during-batch-ci` (no merge while a batch runs) holds the rule. A merge needs a green
   run on the current base (decision `merge-needs-current-base`). A head that lacks the base tip is
   refused, except a small move.
   "No conflicts" does not prove the lanes work together. A green integration run does not prove that
   no line was lost either. Run `lint/check_silent_undo.py` before the merge. First run `git fetch origin <base>`. Then pass `--upstream origin/<base>`, the PR's base branch, `--head <head SHA>`, the PR's head commit, and `--strict`, as CI does. Without `--strict`, a local run exits 0 on UNKNOWN, so a skipped check reads as clean.
   GitHub's merge queue needs an organization-owned repo. A personal repo batches by hand or through
   the merge tool.
   **After a batch merges, route the PRs that now conflict with main.** In the same turn as the merge
   report, the batch runner runs `merge --release-check N... --lint N@<live head>:PASS` (the full 40-hex head) on the handed-in
   lane PRs. Without the lint verdicts, every line FAILs on the lint. A line that says `not clean (merge
   conflict)` names a PR that conflicts with the new main. A line that says `unknown` does not say there is a conflict. Route a PR only when the
   conflict is the line's only reason. A line that also says the log was edited needs the full review. A line that also says the log is not done follows the ledger's `lane round n`.
   The runner names each conflicting PR to its lane and picks nothing per PR, so no coordinator pick is
   needed. The owner's ruling holds the route after a PASS fix verifier (record `pr-review-record`, The review
   a changed head owes). On a log with no Fix check line, the ledger and `--fix-check` take one fix verifier
   too, but the record's line on an older head asks for a full review. That clash is open with the
   coordinator. Each named lane does these acts in its own checkout:
   1. Merge main into the lane branch once: `git fetch origin main`, then `git merge origin/main`.
      Resolve the conflicted paths only. Never rebase, never force-push, never edit a path git merged
      without conflict. Push the merge. A review log can only name a head that is live.
   2. Spawn a fresh fix verifier on Sonnet. Its brief opens `Fix check`, and gives the reviewed head (the
      Head of the PR's newest review log), the conflicted paths as the named finding, and that log's
      `Guard or check:` value. The brief names the read: for each conflicted path, `git diff <merge head>^1
      <merge head> -- <path>` and the same with `^2`. `git show --cc` prints nothing for a conflict that
      took one side whole, and `git diff origin/main...<merge head>` holds the lane's whole diff.
   3. Print the log with `merge <pr> --review-record --head <merge head> --kind K --guard G`, then the
      earlier `--round` lines, and `--net-value` and `--grant` when the earlier log has them, copied in,
      then `--fix-check <reviewed head>:reviewer:sonnet:<PASS|FAIL>`. The tool posts nothing: post the
      printed text as a PR comment. The tool refuses a chain it cannot prove (record
      `pr-review-record`, the fix verifier order).
   4. Run `merge --lane-lint <pr>` at the merge head. Then hand in again.
   A PASS ends review only where the log allows it. A change with `Guard or check: yes` still owes
   round 3 and its net-value test. A PR that merges clean needs no fix verifier and no new log: the log
   stays valid (record `pr-review-record`, clean merge survival). It still needs item 4 of this list, because the
   lint verdict names an exact head. A refused chain means that the lane gets the full review of its
   new head. Two examples: a second fix verifier on a head whose first fix verifier is open, and, after a
   PASS fix verifier, a merge whose second parent is not on main. The first fix verifier on a log with
   no Fix check line meets no merge-shape test, so the verifier's read is the check there. The lane never works around the refusal. A FAIL starts a
   new lane at round 1.
   Until the cutover, batch across sessions too (`git-integration-branch-merge`).
9. **Wait without loops.** Wait for the CI-wake notice that follows `gh pr ready`. A push starts no
   notice. In cloud, mark ready by MCP `update_pull_request` `draft: false` (route
   pr-ready-mcp-cloud); the same CI-wake notice is meant to follow (decision `ci-wait-reads-run-status`; unmeasured in cloud), so
   also wait on the PR subscription and a check-in. Never run `gh run watch`. One watch made 131 API calls in one minute (decision
   `ci-wait-reads-run-status`, CI waits read the run status). Never poll with a sleep loop. Repeated
   `gh run view` or `gh pr checks` calls are a poll. To wait for any other condition, use the
   Monitor tool (decision `agents-wait-with-monitor`, agents wait with the Monitor tool). See
   `snippets.md`, section 9.
   A cloud session waits on its PR subscription, with a `send_later` check-in (`git-ci-wait-checks-in`).
   A red run's `ci-done-comment`, from the last job, wakes it (`git-ci-done-comment-wakes`).
10. **Prove each new check red once** (`verification-trust-guard-after-red`; recipe: skill `fresh-prose`,
    Proof). A pipe hides a check's
    exit code. `lint | tail -1` exits 0 when lint fails. So a commit after it runs on a red check.
    Decide on the command's own exit code. See `snippets.md`, section 10.
11. **No CI on a draft.** Run the PR workflow on `opened`, `synchronize`, `reopened` and
    `ready_for_review`. Skip every job while the PR is a draft. The rollup job skips too. Its `if:`
    is `always() && !github.event.pull_request.draft`. A fan-in job with `if: always()` needs its own
    draft guard, or it fails on a draft. Read "Before you skip a required job". Decision
    `draft-until-reviewed` (every PR opens as a draft) holds the rule. A draft cannot merge, so it
    needs no check. Only the integration PR goes ready, once (step 8).
    A workflow that also has `on: push` for all branches still runs on a draft branch.
    `gh pr create --draft` then `gh pr ready` fires two runs. Keep the draft state in the concurrency
    group (step 4). Otherwise the skipped draft run cancels an in-progress ready run.
    Mark ready (`gh pr ready`, or in cloud MCP `update_pull_request`) only after the draft run shows in `gh run list`. A ready sent seconds after the
    PR opens can give both runs `draft=false`. One then cancels the other. Its cancelled check runs
    can stop the merge, even for an admin (PR 381, Sonnet prompt judges).
    After `gh pr ready`, a run of only skipped jobs proves nothing. Wait for a run on the head that
    ran, or dispatch one. See `snippets.md`, section 5b. Never mark ready in the same second as the
    create. The merge tool refuses an all-skipped head. Incidents: PR 352 (per-file checkout in a
    worktree) and PR 360 (rm rules beside a redirect).
12. **Cheap checks first.** Give each expensive job `needs:` the cheap static job. A red static check
    then stops the shards from starting.
13. **Merge tiny jobs (private repos).** Each job bills its minutes rounded up, plus its setup
    (measured; GitHub does not document per-job rounding). Put checks under about a minute into one job. This saves money in private repos only. Standard
    hosted runners are free in public repos. Measure billed minutes and wall time before and after.
    Merged jobs can make the wait longer. For wall time, see step 15.
14. **Cache the install.** Cache the package install. For example, `actions/setup-node` with
    `cache: npm`. Measure the CI step before and after.
15. **Split the slowest job for wall time.** Use it where minutes are free, as in a public repo.
    Step 13 saves money, not time. Split the slowest serial job into parallel jobs.
    `lint/test_windows_split.py` checks that each suite runs in exactly one job, for the Windows, Linux and macOS splits.
16. **Pin every suite in a split-job guard.** The guard must pin each suite's CI step `if:`,
    `shell:` and `!cancelled()`, with no env override. The `MERGE_TESTS` gap, found in review of
    PR 293 (the Windows merge-test slice), is the case for it. A CI step's `if:` names only its own
    scope flag, or a non-PR event (step 19).
17. **Slice tests on a slow platform.** On PRs, run a platform-specific test slice. Run the full suite
    on main and nightly, except on macOS (R61): every macOS run takes the slice, and a push to main
    starts no macOS job (a job-level `github.event_name != 'push'`, since a step-level skip still starts
    the runner). The nightly skips when main's head has a green push run and the newest completed
    nightly is green (the `nightly-skip` job), and `scope` waits on that job, so nothing is cancelled.
18. **Profile before you refactor test setup.** Compare setup time to test-body time. If the saving is
    under 20%, stop.
19. **Run one scope job first.** Make it a cheap Linux job named `scope`. Every other job needs it.
    A scope skip sits on the CI step that runs the suite or lint, never on the job. Decision
    `same-check-kinds` (every repo runs the same check kinds) and decision `main-branch-protection`
    (the required checks on main) hold the rule: the rollup fails a skipped job. A job whose CI steps
    all skip still starts a runner and bills its setup minutes (step 13), macOS most.
    A job-level `if:` holds only the draft guard. A job that runs only off pull
    requests, such as a push-only job, also skips at its CI steps. A job-level trigger guard would
    skip a needed job on every PR, and the rollup would fail on it. Each scoped CI step's `if:` names
    its scope flag and `|| github.event_name != 'pull_request'`, so push, nightly and dispatch runs
    start it. See `snippets.md`, section 19.
    Two jobs may share a flag. A docs-only PR skips the code suites. Lint CI steps still run. An
    unreadable diff or an unmapped path runs everything.

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

Branch protection decides what counts as passing. Decision `same-check-kinds` (every repo runs the
same check kinds) sets the rule. Branch protection requires one check: the `all-jobs-passed` rollup.
That job lists every other job in `needs:`, and its `if:` holds `always()`. The rollup fails a
needed job that failed, was cancelled or was skipped. Without the rollup, a skipped job reads as
passing. So a scoped-out suite skips at its CI step, and its job still runs and passes (step 19).
The rollup skips on a draft, and a draft cannot merge (step 11). Read the protection rule first:
`snippets.md`, section 3b.

The required check names live in the branch protection. `merge.requiredChecks` in
`.github/stamp.json` says `"protection"`, so `merge` reads them from there. A repo that pins a list
in `stamp.json` instead must keep it equal to the protection. `merge` refuses a disagreement. A
rename edits the protection. A PUT on the protection API replaces the whole rule. It drops any field
you leave out (decision `main-branch-protection`, the required checks on main).

## Docs

CI claims in README or docs go stale too. See the `fresh-prose` skill.

## Opt-in templates

Each template has one home: a composite action under `actions/<name>/`, or a plain file (decision
`opt-in-ci-templates-composite`, opt-in templates are composite actions). Adopt an action with
`uses: shivinate7/claude-settings/actions/<name>@<full-sha>`, or copy the file. Each line below
gives the action's purpose from its `action.yml`.

The seven opt-in templates of that decision:

- `all-jobs-passed`: fan-in check. Fails when a needed job failed, was cancelled or was skipped.
  The caller sets `needs: [...]`, `if: always()`, and `with: needs: ${{ toJSON(needs) }}`.
- `ci-done-comment`: posts one PR comment when a run ends with a failed or cancelled job. The caller
  is the last job. It sets `needs:` on every other job,
  `if: ${{ !cancelled() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}`,
  `permissions: {pull-requests: write}`, and `with: needs: ${{ toJSON(needs) }}`.
- `ci-alarm`: opens or comments on one issue when the latest completed run per workflow and per
  event group on a branch (default `main`) is red. Groups: `actions/ci-alarm/events.json`. Runs of
  other events, such as a Pages build, a `workflow_run` or a `repository_dispatch`, and runs of a
  deleted workflow, are not judged. A failed `gh` read prints `unknown` with a warning, never a red
  job. The caller is a scheduled workflow with `permissions: {actions: read, issues: write}`. It
  needs no checkout. Not enabled in this repo.
- `readme-links`: checks the external https links in a markdown file (default `README.md`). Run it
  from a weekly schedule, never per PR. `open-issue: true` opens or updates one issue.
- `ruling-kind`: fails a PR that adds or edits a record with no valid Kind line. The caller needs
  checkout at `fetch-depth: 0`. It fails closed when the base cannot be read.
- `claude-md-cites`: fails a run when a unit of the caller's `CLAUDE.md` files or `.claude/**/*.md` copies
  claude-settings record text instead of naming the record. The caller needs checkout first.
- `githooks/main-ref`: refuses a local move of main to a commit that origin lacks. Run
  `sh githooks/main-ref/install.sh` in each clone. `sh githooks/main-ref/install.sh --check` writes
  nothing and compares each armed copy to main; the shared pre-commit runs it and refuses a commit
  while a copy is missing or behind main.
- `testing/skip-locally-fail-in-ci.mjs`: wrap an env-dependent probe in `needEnv`. It skips locally,
  and fails when `CI` is set.

The other composite actions in `actions/`, in the same home:

- `code-check`: one type check and one lint for defects per language. The caller needs checkout at
  `fetch-depth: 0` and setup-python.
- `zizmor`: audits the caller's workflows and actions with one pinned zizmor (input `paths`, default
  `.github/`). The caller needs checkout and pipx on PATH. `run.sh` holds the pin.
- `playwright-setup`: installs the Playwright that a lockfile pins, and its browsers. No apt step by
  default.
- `ste-lint`: runs `lint/ste_lint.py` on changed Markdown, or on every file with `scope: all`.
- `stamp`: runs `stamp.mjs --check` on the records. A pending record on the default branch fails it.

## Audit a repo

Run these checks against `.github/workflows/*.yml` and the branch protection. Answer yes or no, or
n/a where an item says so. A no is a finding. A read that cannot run is unknown, never yes or no (rule
`verification-report-unknown-reads`, report a read that cannot run as unknown).

1. Does a job named `all-jobs-passed` exist? Read `.github/workflows/*.yml`.
2. Does that job list every other job in `needs:`, except `ci-done`, with `if:` holding `always()` and
   the draft guard? Read its job block. A job skipped by design may stay off `needs:` when its own
   job-level `if:` skips it on every `pull_request` event, such as a nightly-only or push-only job. A
   PR can then never turn it red. Read that job's `if:`. A job off `needs:` that can run on a PR is a no.
3. Does branch protection require exactly one check, `all-jobs-passed`? Read
   `gh api repos/<owner>/<repo>/branches/main/protection`, and count `required_status_checks.checks`.
   A 403 is unknown.
4. Do the PR triggers include `opened`, `synchronize`, `reopened` and `ready_for_review`? Read each
   `on: pull_request: types:` line.
5. Does every job skip on a draft, directly or through `needs:`? Read each job's `if:` and `needs:`.
6. Does the top-level `concurrency:` group hold the PR draft state, and never cancel a default-branch
   run? Read the block. Compare it with `snippets.md`, section 4.
7. Does every job set `timeout-minutes`? Run `grep -c "^    runs-on:"` and
   `grep -c "^    timeout-minutes:"` on each workflow file. The two counts must match.
8. Is every `uses:` pinned by a full 40-character SHA, except same-repo `$/` actions? Run
   `grep -n "uses:" .github/workflows/*.yml` and read each line. A local `./` call is a finding under
   zizmor 1.30.0 or later (step 7).
9. Does every `actions/checkout` set `persist-credentials: false`? Run
   `grep -n -A3 "actions/checkout" .github/workflows/*.yml`.
10. Is the top-level `permissions:` read-only, with `contents: read` or narrower? Read the lines above
    `jobs:` in each workflow.
11. Is there no `pull_request_target` that checks out the PR head? Run
    `grep -n "pull_request_target" .github/workflows/*.yml`. For each hit, read its `ref:`.
12. Does every job-level `if:` hold only the draft guard, or the guard of `ci-done`? Run
    `grep -n "^    if:" .github/workflows/*.yml`. A scope flag or a trigger guard at job level is a
    finding. It skips a needed job. A job that no rollup needs is judged by items 1 and 2 instead, so
    do not flag it here.
13. If sessions wait on this repo's CI, is the last job `ci-done`, with `needs:` every other job and a
    call to `ci-done-comment`? Read the last job block. A repo no session waits on answers n/a.
14. Does no `run:` pipe a check into `tail` or `head` without `set -o pipefail`? Run
    `grep -nE "\| *(tail|head)" .github/workflows/*.yml`. Read each hit. A version print that decides
    no verdict is not a finding.
15. Does an audit step run in CI, with a pinned version? Run
    `grep -n "zizmor" .github/workflows/*.yml`, then read each zizmor step to the next `- ` step line. A
    version given as `zizmor==<x.y.z>`, or as that step's own `with:` input such as `version: <x.y.z>`,
    is a yes. A `version:` in another step is not the zizmor pin. A step
    that runs the shared action (`actions/zizmor@<sha>` or `$/actions/zizmor`) is also a yes: its
    `run.sh` holds the pin. No version and no shared action is a no.
