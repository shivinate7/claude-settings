# A lane never runs a full CI job

## The ruling

Owner, 2026-10-27 (waiting page item 27, option a): a lane runs only the suites its change touches. It never runs a whole CI job locally, `bin/ci-job` included. The batch's integration CI run is the only full run (`roles-each-layer-proves-once`, each layer proves a change once). `bin/ci-job` stays, as a tool any session may run on demand. One exception: a lane runs `bin/ci-job gates --lint --base origin/main` before it joins a batch. That mode runs only the fast `python3 lint/...`, `python3 actions/...` and `bin/ste-changed` steps, chosen from the step commands in gates.yml. It runs no hook suite and no mutation test. For the STE lint `uses:` action, it runs `bin/ste-changed <base>`. With no `--base`, `--lint` takes `origin/main` and says so, or prints one unknown line and exits 2 when `origin/main` is absent. Why: a no-base run skipped the pull-request steps and read as a pass (incident 2026-10-28, batch 5: the comment narration check then failed in CI).

Why: a full local run per lane proves again what the batch run proves, and costs a lane its time. A fixture that copies a changed file is caught by the batch run, and the fixtures now copy what git tracks, so a new shared module no longer breaks them.

Kind: process
Home: rule:roles-each-layer-proves-once
