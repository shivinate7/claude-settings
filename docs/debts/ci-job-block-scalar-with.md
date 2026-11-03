# ci-job reads a block-scalar with: value as its marker

**What.** `bin/ci-job --lint` reads a step's `with: paths: |` (or `>`) as the literal `|` or `>`, and an inline `# comment` stays in the value. The zizmor step then fails with "invalid input: |" on a correct workflow. A child repo that switches to `actions/zizmor` and writes its paths as a block hits it.

**Where.** `bin/ci-job`, the zizmor branch of `plan()`, through `step_with` in `lint/workflow_steps.py`.

**Decision.** `action-pins-follow-sessions`, CI pins follow the session's tools (ci-job runs the shared actions in place).

**Retire.** `step_with` reads a block scalar and drops an inline comment. Or `plan()` returns unknown for a value it cannot read. Closed when a red case in `lint/test_ci_job.py` with `paths: |` over two lines passes both paths to run.sh.
