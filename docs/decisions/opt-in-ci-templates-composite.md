# Opt-in CI templates are composite actions

## The ruling

Nine templates any repo can adopt live in one home and one shape: a composite action under
`actions/<name>/`, or a plain file where the template is no CI step.

| Template | Home |
| --- | --- |
| All-jobs-passed check | `actions/all-jobs-passed` |
| CI done comment on a red run | `actions/ci-done-comment` |
| Nightly CI alarm | `actions/ci-alarm` (also holds `issue.sh`, the one open-or-comment helper; opt-in `dropped-start` flags a pull request whose check run never started) |
| Weekly README link check | `actions/readme-links` (calls `ci-alarm/issue.sh`) |
| Starter CI quick checks for a repo with no CI | `actions/quick-checks` (its `quick_checks.py` runs the links, scripts and JSON checks on the caller's checkout; the starter CI template is `skills/project-ops/templates/starter-ci/checks.yml`, and `bin/ci-job` runs the action under `--lint`) |
| Ruling kind check on a pull request | `actions/ruling-kind` (runs `lint/check_ruling_kind.py` on the caller's checkout) |
| Main-ref refusal hook | `githooks/main-ref` (its `install.sh` copies it) |
| Pre-commit secrets and symlink hook | `githooks/pre-commit` (its `install.sh` copies it) |
| Skip locally, fail in CI | `testing/skip-locally-fail-in-ci.mjs` |

Why composite, not `workflow_call`:

- `actions/ste-lint` and `actions/stamp` are composite and q_max consumes them with `uses: <repo>/actions/<name>@<sha>`. A second shape would be a second home.
- The check must be a CI step in the caller's own job. Its check name stays fixed, and the caller sets `needs` and `if: always()`. A reusable workflow adds a nested job name and cannot read the caller's `needs`.
- The caller keeps the trigger, `permissions`, runner and `timeout-minutes`. A reusable workflow would hide the grant that zizmor should see.
- Logic lives in a script beside `action.yml`. The test runs that script, so the test and the action cannot drift.

The main-ref hook lets local main move only to a commit origin already has. `gh pr merge` runs on GitHub and moves no local ref.

The pre-commit hook reads the index. It refuses a staged environment file, which a wildcard stage (`git add -A`, `git add .`) takes in, and a symlink that is absolute or points outside the repo. The mistake: a wildcard stage commits secrets to a public repo, and an outside symlink lets a later write or delete reach past the repo (banchi decision D47, 2026-08-29: a symlink lost a 133 MB mirror; source: the child-guard-promotion plan, banchi row 20, PR #1119). The env name test is `names_env_file` in `hooks/guard_env.py`, read from the installed hooks. `PRE_COMMIT_GUARD=off` lets one commit through.

`checks.yml` runs 15 template test commands in one CI step, "Opt-in CI template fixture suites", in the `checks` job. It calls one template, `ci-done-comment`, because this repo's own sessions wait on its CI (decision ci-wait-reads-run-status, "The cloud wake"). CI templates are opt-in per repo, so a repo with no CI is never stuck on red checks. The nightly alarm is not enabled.

A CI alarm on a push to main wakes the batch runner and opens no issue (owner ruling R53, 13:07 CST Nov 12). `actions/ci-alarm/wake.sh` is the one home of that wake, and `test_wake.sh` tests it. Per the coordinator's pick (13:12 CST Nov 12), it comments on the earliest merged pull request into main that holds the commit. It needs `REPO`, `SHA`, `KEY`, `TEXT` and `GH_TOKEN`. The hidden marker `<!-- main-alarm:KEY -->` in that comment is the memory: a pull request that holds it gets no second comment. A commit with no pull request merged into main opens no issue. The script then exits non-zero with the message in the step summary, so the caller's job ends red. No job calls it yet.

Cost: per alarm, `actions/ci-alarm/wake.sh` (tested by `actions/ci-alarm/test_wake.sh`) makes at most one read of the pull requests for the commit. If a pull request merged into main holds the commit, it reads that pull request's comments: one read per 100 comments, at least one. It writes at most one comment, and only when the marker is absent. If none does, it reads no comments and writes no comment. A failed read or post, or a commit with no pull request, writes one message to GITHUB_STEP_SUMMARY when that variable is set, else to stderr, and exits 1. It has no retry or poll loop and no timer, and it starts no long-lived process. Time and bytes per alarm: (unmeasured).

Each template ships a test that goes red on its defect (`test_action.sh`, `test_comment.py`, `test_readme_links.py`, `test_hook.sh`, `test_pre_commit.sh`, `skip-locally-fail-in-ci.test.mjs`).

Kind: process
Home: rule:building-one-home-per-capability
