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
- Both harnesses also run when `.github/scripts/harness-scope.sh` or
  `.github/workflows/gates.yml` changes. A break in the scope logic then shows on the
  pull request, not only in the nightly run.
- `lint/_transcript.py` is in the guard set because the ruling names it. No harness
  imports it.
- The diff uses `--no-renames`. A move out of a trigger path then lists the old path.
- An empty base SHA on a pull request runs every harness. So does an empty or
  all-zeros `before` SHA on a push.
- A nightly `schedule:` run on main and `workflow_dispatch` run every harness. The guard harness
  runs on ubuntu only; the sweep harness runs on every OS.
- A diff that cannot be read runs both harnesses.
- The Guard harness runs on Ubuntu only (the `gates` job). macOS and Windows never run it: on
  main's push run 37086259145 it took 34.5 min on Windows and hit the 45 min job timeout. No
  mutant is marked `windows` or macOS-only, so no subset stays on those OSes.

## Accepted risk

main has no branch protection and no required check, so a skipped step blocks nothing.
A regression that reaches a harness only through a file outside the sets above is
caught by the nightly run, not by the pull request.
