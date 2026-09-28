# ci-hygiene snippets

## 1. Rank step times of a run

```sh
gh run view <run-id> --json jobs --jq '
  .jobs[] | .name as $j | .steps[]
  | [((.completedAt|fromdate)-(.startedAt|fromdate)), $j, .name] | @tsv' \
  | sort -rn | head
```

## 3. Gate a slow check on its inputs

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
              echo "$files" | grep -Eq '^(src/|slow-check/)' || slow=false
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

## Required jobs that skip

```sh
gh api repos/<owner>/<repo>/branches/<branch>/protection
```

A required job that is skipped reports as passing. A required job that never starts, because of
a path filter on the whole workflow, blocks the merge. Prefer `if:` on the job.

## 4. Cancel superseded runs

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## 5. Pin and audit

```yaml
- uses: actions/checkout@<full-40-char-sha>  # v4.2.2
  with: {persist-credentials: false}
```

Same-repo action: `uses: ./path/to/action`.

`.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule: {interval: weekly}
    cooldown: {default-days: 7}
```

Audit with zizmor. Run it locally with the same command and path set as CI, and include
`dependabot.yml`:

```sh
zizmor .github/workflows .github/dependabot.yml
```

## 7. Wait without loops

```sh
gh run watch <run-id> --exit-status > watch.log 2>&1   # run in the background
```

Read `watch.log` when it exits. Never send the output to `/dev/null`.

## 8. Prove a gate red

```sh
cp -R . "$(mktemp -d)/scratch" && cd "$_"   # scratch copy
# break one target, for example replace one pinned SHA with a tag
zizmor .github/workflows .github/dependabot.yml   # must exit non-zero
```
