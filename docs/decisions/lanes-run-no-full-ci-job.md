# A lane never runs a full CI job

## The ruling

Owner, 2026-10-27 (waiting page item 27, option a): a lane runs only the suites its change touches. It never runs a whole CI job locally, `bin/ci-job` included. The batch's integration CI run is the only full run (`roles-each-layer-proves-once`, each layer proves a change once). `bin/ci-job` stays, as a tool any session may run on demand. One exception: a lane runs `merge --lane-lint <pr>` before it hands off, and the batch runner runs it again before the join. `merge --lane-lint` runs `bin/ci-job checks --lint --base origin/<base>` at the lane head. That mode runs only the fast `python3 lint/...`, `python3 actions/...` and `bin/ste-changed` steps, chosen from the step commands in checks.yml. It runs no hook suite and no mutation test. For the STE lint `uses:` action, it runs `bin/ste-changed <base>`. With no `--base`, `--lint` takes `origin/main` and says so, or prints one unknown line and exits 2 when `origin/main` is absent. Why: a no-base run skipped the pull-request steps and read as a pass (incident 2026-10-28, batch 5: the comment narration check then failed in CI). With `--base`, ci-job sets `GITHUB_BASE_REF` in each step, as the runner does on a pull request, so a lane that adds a record is not red for its stale records page.

The gate (incident 2026-11-01, batches 59 and 60: lane PRs #974, #979, #984, #990 and #1004 joined with shellcheck, ruling kind or STE reds). Both sides run `merge --lane-lint <pr>`, which runs that same `--lint` in a temporary worktree at the lane's head.

- The lane runs it before it hands its PR and head off. A red lane does not hand off.
- The batch runner runs it on each lane head before the join. It refuses a red lane, and that lane fixes and hands off again.
- A FAIL refuses. An unknown refuses unless `--lint-unknown-ok "<reason>"` is given, and the reason is logged.

Cost: one ci-job run (about 550 s to 660 s, 4 runs on 2026-11-01) and one worktree per call. It runs once at hand-off and once per lane at the join. It writes one ci-job log, and keeps no other file.

Why: a full local run per lane proves again what the batch run proves, and costs a lane its time. A fixture that copies a changed file is caught by the batch run, and the fixtures now copy what git tracks, so a new shared module no longer breaks them.

Kind: process
Home: rule:roles-each-layer-proves-once
