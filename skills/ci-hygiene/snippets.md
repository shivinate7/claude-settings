# ci-hygiene snippets

## 1. Rank step times of a run

```sh
gh run view <run-id> --json jobs --jq '
  .jobs[] | .name as $j | .steps[]
  | [((.completedAt|fromdate)-(.startedAt|fromdate)), $j, .name] | @tsv' \
  | sort -rn | head
```

Read the billed minutes each week. The `user` scope is the scope that worked here, and the docs
name none. The endpoint works only for accounts on the enhanced billing platform:

```sh
gh auth refresh -s user
gh api /users/<owner>/settings/billing/usage --jq '.usageItems[] | select(.product=="actions")'
```

No template: a workflow token cannot read this endpoint, so an alarm would need a stored
personal token. Set the budget alarm in the billing settings (Budgets and alerts) instead.

## 3a. Run a slow check only when its inputs change

```yaml
on:
  push:
  pull_request:
  schedule: [{cron: "0 3 * * *"}]   # nightly full run
  workflow_dispatch:
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      slow: ${{ steps.d.outputs.slow }}
    steps:
      - uses: actions/checkout@<full-sha>  # v4.x.x
        with: {fetch-depth: 0, persist-credentials: false}
      - id: d
        env:
          EVENT: ${{ github.event_name }}
          BASE: ${{ github.event.pull_request.base.sha || github.event.before }}
        run: |
          slow=true                                   # fail safe: run
          if [ "$EVENT" = push ] || [ "$EVENT" = pull_request ]; then
            if files=$(git diff --name-only "$BASE" HEAD 2>/dev/null) && [ -n "$files" ]; then
              grep -Eq '^(src/|slow-check/)' <<< "$files" || slow=false
            fi
          fi
          echo "slow=$slow" >> "$GITHUB_OUTPUT"
  slow-check:
    needs: detect
    if: needs.detect.outputs.slow == 'true'
    runs-on: ubuntu-latest
    steps: []   # the slow check
```

Replace the grep pattern with the paths the check reads. Schedule and manual runs skip
detection, so `slow` stays true.

## 3b. Required jobs that skip

```sh
gh api repos/<owner>/<repo>/branches/<branch>/protection
```

A required job that is skipped reports as passing. A required job that never starts, because of
a path filter on the whole workflow, blocks the merge. Prefer `if:` on the job.
Require a matrix through one fan-in job with `if: always()`. Its check name stays fixed when the
matrix changes.

Rename a required check in both places: `merge.requiredChecks` in `.github/stamp.json`, and the
protection rule. A PUT needs an admin login. Push rights are not enough. A PUT replaces the whole
rule, so send every field from the read above, with the new names:

```sh
gh api -X PUT repos/<owner>/<repo>/branches/<branch>/protection --input <json>
```

## 4. Cancel superseded runs

```yaml
concurrency:
  # A main, nightly or manual run gets its own group: GitHub keeps one pending run per group and
  # replaces it even with cancel-in-progress false, so a shared group can drop a merge's verdict.
  # The PR draft state is in the group: a draft run (skips every job) must not cancel a ready run.
  group: ${{ github.workflow }}-${{ (github.ref == format('refs/heads/{0}', github.event.repository.default_branch) || github.event_name == 'schedule' || github.event_name == 'workflow_dispatch') && github.run_id || format('{0}-{1}', github.ref, github.event.pull_request.draft) }}
  cancel-in-progress: ${{ github.ref != format('refs/heads/{0}', github.event.repository.default_branch) && github.event_name != 'schedule' && github.event_name != 'workflow_dispatch' }}   # never cancel a main, nightly or manual run
```

## 5a. No CI on a draft

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
jobs:
  static:
    if: ${{ !github.event.pull_request.draft }}
    runs-on: ubuntu-latest
    steps: []   # the cheap checks, in one job
  shards:
    needs: static   # a red static job stops the shards
    if: ${{ !github.event.pull_request.draft }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-sha>  # v4.x.x
        with: {persist-credentials: false}
      - uses: actions/setup-node@<full-sha>  # v4.x.x
        with: {node-version: 22, cache: npm}
      - run: npm ci
```

A skipped `needs` job skips the job that needs it, so `if:` on `shards` stays: a draft skips both.
A fan-in job (`all-jobs-passed`) runs on `if: always()` and fails on a skipped need. Give it
`if: ${{ always() && !github.event.pull_request.draft }}`, so a draft skips it too.

## 5b. Prove the head after `gh pr ready`

```sh
gh run list --commit <head-sha> --json name,status,conclusion   # completed, and not skipped
gh workflow run <workflow-file> --ref <branch>           # none ran: dispatch one
```

`gh workflow run` needs a `workflow_dispatch` trigger in the workflow.

## 6. Read every run after a merge

```sh
gh run list --commit <merge-sha> --json name,conclusion
```

## 7. Pin and audit

```yaml
- uses: actions/checkout@<full-40-char-sha>  # v4.2.2
  with: {persist-credentials: false}
```

Same-repo action: `uses: $/path` (GitHub changelog 2026-07-30) or `uses: ./path`.

This repo's `.github/dependabot.yml` ignores every version update for `github-actions`:

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    ignore:
      - dependency-name: "*"
        update-types: ["version-update:semver-major", "version-update:semver-minor", "version-update:semver-patch"]
```

Renovate (`renovate.json`) tracks three custom pins. It does not track actions.

Audit with zizmor. Run the CI command from the repo root. It is the zizmor step of
`.github/workflows/checks.yml`:

```sh
pipx run zizmor==1.30.1 .github/ actions/
```

## 9. Wait without loops

```sh
gh pr ready <pr-number>                               # the CI-wake hook waits and wakes you
gh run view <run-id> --json status,conclusion         # one read, after the notice
```

Never run `gh run watch`: it makes about 131 API calls a minute. Never send a command's output
to `/dev/null`.

## 10. Prove a check red

```sh
cp -R . "$(mktemp -d)/scratch" && cd "$_"   # scratch copy
# break one target, for example replace one pinned SHA with a tag
pipx run zizmor==1.30.1 .github/ actions/   # must exit non-zero
```

Let the check's own exit code decide a commit. A pipe takes the exit code of its last command:

```sh
# Wrong: tail's exit code is the pipe's. A red check still commits.
<check> | tail -1 && git commit -m "<subject>"
# Right: the check's exit code decides. Its output goes to a log.
if <check> > check.log 2>&1; then git commit -m "<subject>"; else tail -n 20 check.log; fi
```

In bash, `set -o pipefail` makes a pipe fail when any stage fails.

## 11. Public repos: visibility, fork PRs, least privilege

Docs checked 2026-10-12.

Read the visibility first. The answer is `PUBLIC`, `PRIVATE` or `INTERNAL`:

```sh
gh repo view --json visibility
```

Fork PRs. Secrets are not passed to a fork's `pull_request` run, except `GITHUB_TOKEN`. That token is
read-only there.
Source: https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request

Least privilege. Set `permissions` at the top level, and raise it on one job only when that job needs
more. An unset key inherits the repo or org default.
Source: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#permissions

```yaml
on:
  pull_request:
permissions:
  contents: read   # default for every job
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-sha>  # v4.x.x
        with: {persist-credentials: false}
```

Pin every third-party action by full SHA. A full-length SHA guards against a backdoor added to the action's repository.
Source: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions

`pull_request_target`. This trigger runs the default branch with secrets and write access. Do not
check out the PR's head in it. Do not write this:

```yaml
on: pull_request_target
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          ref: ${{ github.event.pull_request.head.sha }}   # refused: fork code runs with secrets
```

Source: https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#pull_request_target
and https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions

Billing. Standard GitHub-hosted runners are free for public repos.
Source: https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions
