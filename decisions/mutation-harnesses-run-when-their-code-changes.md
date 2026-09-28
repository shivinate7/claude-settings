# Mutation harnesses run when their code changes, and every night

## What was measured

In the latest green main run, the Guard mutation harness took 33.5 min on macOS and
25.6 min on Linux. The Janitor sweep mutation harness took 17.4 min on macOS. Every
other step took under 2 min. A pull request that changed one sentence in
`agents/builder.md` waited 25 to 70 min.

## The ruling

- `.github/scripts/harness-scope.sh` reads `git diff --name-only` against the merge
  base and sets one output per harness. Each harness step reads that output.
- Guard harness runs when `hooks/**` or `lint/_transcript.py` changes. The guard and its
  suites import only the standard library, so `hooks/**` is the whole import set.
- Janitor harness runs when `janitor/**`, `hooks/guard.py`, `hooks/mutate_shared.py`
  or `settings.json` changes. The janitor imports guard, the harness imports
  `mutate_shared`, and the session-end suite reads `settings.json`.
- A nightly `schedule:` run on main and `workflow_dispatch` run every harness on every OS.
- A diff that cannot be read runs both harnesses.
- The earlier choices stay: macOS and Windows skip the Guard harness on pull requests.

## Accepted risk

main has no branch protection and no required check, so a skipped step blocks nothing.
A regression that reaches a harness only through a file outside the sets above is
caught by the nightly run, not by the pull request.
