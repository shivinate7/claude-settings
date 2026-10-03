# Opt-in CI templates are composite actions

Owner approved five templates any repo can adopt. They live in one home and one shape:
a composite action under `actions/<name>/`, or a plain file where the template is no workflow
step.

| Template | Home |
| --- | --- |
| All-jobs-passed gate | `actions/all-jobs-passed` |
| Nightly CI alarm | `actions/ci-alarm` (also holds `issue.sh`, the one open-or-comment helper) |
| Weekly README link check | `actions/readme-links` (calls `ci-alarm/issue.sh`) |
| Main-ref refusal hook | `githooks/main-ref` (`install.sh` copies it) |
| Skip locally, fail in CI | `testing/skip-locally-fail-in-ci.mjs` |

## Why composite, not `workflow_call`

- `actions/ste-lint` and `actions/stamp` are composite and q_max already consumes them with
  `uses: <repo>/actions/<name>@<sha>`. A second shape would be a second home.
- A reusable workflow is a whole job. The gate must be a step in the caller's own job, because
  its check name stays fixed and the caller sets `needs` and `if: always()`. A reusable
  workflow adds a nested job name to the check and cannot read the caller's `needs`.
- The caller keeps the trigger, `permissions`, runner and `timeout-minutes`. A reusable
  workflow would hide the grant that zizmor should see in the caller.
- Logic lives in a script beside `action.yml`. The test runs that script, so the test and the
  action cannot drift.

## Reconciling the hook with `hooks/guard.py`

`guard.py` rule 6 (`merge-main`) allows `gh pr merge`. That merge runs on GitHub and moves no
local ref, so the hook never sees it. The next `git pull` moves local main to a commit origin
already has, and the hook allows that (an ancestor of `origin/main`). The hook refuses a ff,
reset, `branch -f`, `update-ref` or delete that lands on a commit origin lacks. The two agree:
the guard allows the act that merges, the hook refuses the act that bypasses it.

## Red proof

Each template ships a test that goes red on its defect (`test_action.sh`,
`test_readme_links.py`, `test_hook.sh`, `skip-locally-fail-in-ci.test.mjs`). The hook test
was run with the hook off (`MAIN_REF_GUARD=off`): 6 cases failed. `act` is not installed, so
the gate and the alarm are proved on their scripts, not on a hosted runner. The composite
`action.yml` wrappers are unmeasured on a real run.

## Not wired

`gates.yml` runs the five tests. It does not call the templates: the owner chose no required
checks on main. The nightly alarm is proposed in the PR, not enabled.
