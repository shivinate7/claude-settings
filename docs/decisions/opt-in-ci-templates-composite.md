# Opt-in CI templates are composite actions

## The ruling

Seven templates any repo can adopt live in one home and one shape: a composite action under
`actions/<name>/`, or a plain file where the template is no CI step.

| Template | Home |
| --- | --- |
| All-jobs-passed guard | `actions/all-jobs-passed` |
| CI done comment on a red run | `actions/ci-done-comment` |
| Nightly CI alarm | `actions/ci-alarm` (also holds `issue.sh`, the one open-or-comment helper) |
| Weekly README link check | `actions/readme-links` (calls `ci-alarm/issue.sh`) |
| Ruling kind check on a pull request | `actions/ruling-kind` (runs `lint/check_ruling_kind.py` on the caller's checkout) |
| Main-ref refusal hook | `githooks/main-ref` (its `install.sh` copies it) |
| Skip locally, fail in CI | `testing/skip-locally-fail-in-ci.mjs` |

Why composite, not `workflow_call`:

- `actions/ste-lint` and `actions/stamp` are composite and q_max consumes them with `uses: <repo>/actions/<name>@<sha>`. A second shape would be a second home.
- The guard must be a CI step in the caller's own job. Its check name stays fixed, and the caller sets `needs` and `if: always()`. A reusable workflow adds a nested job name and cannot read the caller's `needs`.
- The caller keeps the trigger, `permissions`, runner and `timeout-minutes`. A reusable workflow would hide the grant that zizmor should see.
- Logic lives in a script beside `action.yml`. The test runs that script, so the test and the action cannot drift.

The main-ref hook lets local main move only to a commit origin already has. `gh pr merge` runs on GitHub and moves no local ref.

`checks.yml` runs the seven tests. It calls one template, `ci-done-comment`, because this repo's own sessions wait on its CI (decision ci-wait-reads-run-status, "The cloud wake"). CI templates are opt-in per repo, so a repo with no CI is never stuck on red checks. The nightly alarm is not enabled.

Each template ships a test that goes red on its defect (`test_action.sh`, `test_comment.py`, `test_readme_links.py`, `test_hook.sh`, `skip-locally-fail-in-ci.test.mjs`).

Kind: process
Home: rule:building-one-home-per-capability
