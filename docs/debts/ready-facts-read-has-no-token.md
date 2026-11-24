# The ready run's Facts step has no token

**What.** The ready step's local run of "Rules and records move together" reads GitHub for each `Facts:` claim with no token. `bin/ci-job` maps `github.token` to "" (:1101), and `child_env` strips the inherited `GH_TOKEN` (:824). So `fact_value` raises CannotRun, the step reads unknown, and the ready mark refuses. No record holds a Facts line today, so nothing refuses now. The Facts PASS is saved 7 days under a key with no live GitHub state (:127-135, :836-843), so a PASS saved with a token could replay after the PR changes. No token reaches the step today, so no such PASS exists yet.

**Where.** `lint/compliance_probes.py`, `fact_value` (:1702-1721; raises CannotRun without GITHUB_TOKEN or GH_TOKEN). `actions/claude-md-cites/action.yml`, the Facts step (:27-32; `GITHUB_TOKEN: ${{ github.token }}`). `bin/ci-job`: `RUNNER_UNSET` (:336), `child_env` (:824), the `github.token` value (:1101), the rerun cache (:127-135; key :836-843). `.github/stamp.json` `merge.readyChecks` names the step.

**Decision.** `lanes-run-no-full-ci-job` (a lane never runs a full CI job).

**Retire.** Closed when a case in `lint/test_ci_job.py` shows the ready run's Facts step gets a token, or is skipped locally with a line that says so.
