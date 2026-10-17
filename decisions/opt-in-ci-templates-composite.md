# Opt-in CI templates are composite actions

## The ruling

Six templates any repo can adopt live in one home and one shape: a composite action under
`actions/<name>/`, or a plain file where the template is no workflow step.

| Template | Home |
| --- | --- |
| All-jobs-passed gate | `actions/all-jobs-passed` |
| Nightly CI alarm | `actions/ci-alarm` (also holds `issue.sh`, the one open-or-comment helper) |
| Weekly README link check | `actions/readme-links` (calls `ci-alarm/issue.sh`) |
| Ruling kind check on a pull request | `actions/ruling-kind` (runs `lint/check_ruling_kind.py` on the caller's checkout) |
| Main-ref refusal hook | `githooks/main-ref` (`install.sh` copies it) |
| Skip locally, fail in CI | `testing/skip-locally-fail-in-ci.mjs` |

Why composite, not `workflow_call`:

- `actions/ste-lint` and `actions/stamp` are composite and q_max consumes them with `uses: <repo>/actions/<name>@<sha>`. A second shape would be a second home.
- The gate must be a step in the caller's own job. Its check name stays fixed, and the caller sets `needs` and `if: always()`. A reusable workflow adds a nested job name and cannot read the caller's `needs`.
- The caller keeps the trigger, `permissions`, runner and `timeout-minutes`. A reusable workflow would hide the grant that zizmor should see.
- Logic lives in a script beside `action.yml`. The test runs that script, so the test and the action cannot drift.

The hook agrees with `hooks/guard.py` rule 6 (`merge-main`). `gh pr merge` runs on GitHub and moves no
local ref. The next `git pull` moves local main to a commit origin already has, and the hook allows
that. The hook refuses a ff, reset, `branch -f`, `update-ref` or delete that lands on a commit origin lacks.

`gates.yml` runs the six tests. It does not call the templates. The nightly alarm is not enabled.
The gate and the alarm are proved on their scripts, not on a hosted runner. The `action.yml` wrappers
are unmeasured on a real run.

Each template ships a test that goes red on its defect (`test_action.sh`, `test_readme_links.py`,
`test_hook.sh`, `skip-locally-fail-in-ci.test.mjs`).

## Holes, named

Debt `ste-exclude-star-crosses-dir` (an STE-lint exclude star can skip files in deeper folders).

Kind: process
Home: rule:building-one-home-per-capability
