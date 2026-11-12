# A roadmap step waits on a step slug, never on a bare PR number

## The ruling

Owner chat, 13:09 CST Nov 10, relayed by the coordinator at 13:14 CST, made the ask. The step `dead-pr-waits` records that ask in its `note` field, without the 13:09 words.

The owner's verbatim words are from owner chat, 13:10 CST Nov 10, relayed by the coordinator at 13:18 CST: "it needs to be mechanized either where things are placed or where things are checked".

Source for both: `roadmap/data/steps/dead-pr-waits.json` on branch `roadmap`, field `note`. The rule in that note: a step waits on a step slug (`blockedBy`), never a bare PR number.

The coordinator measure (step `why`, 13:05 CST Nov 10) found 26 of 737 open steps waiting on a PR GitHub shows closed and unmerged, so nobody acts on them.

- Placement: guard rule `dead-pr-wait` (`dead_pr_wait_hit` in `hooks/guard_merge.py`, run by `hooks/guard.py`). It refuses a Write, Edit or MultiEdit to `roadmap/data/steps/<name>.json` that adds a wait on `#N` or `PR #N` to the step's `title`, `why`, `note` or `ask`. It also refuses a write that clears the `blockedBy` slug from a step whose bare wait stays (`cleared` in `dead_pr_wait_hit`). It refuses only when the step it leaves has no slug in `blockedBy`. `hooks/test_guard.py` lists these cases under `dead-pr-wait`. The wait words are `DEAD_PR_WAIT_PHRASES` in `hooks/shared_names.py`, which the guard and the build's `dead PR wait` line both read.
- Check: the roadmap build (`dead_pr_waits` in `skills/roadmap/build.py`) prints a `dead PR wait` line only for an open step (status not `done`) that waits on a PR the live file's `prStates` shows closed and not merged. That line reads `waits on #N, which is closed and not merged`. The build exits 1 when any line reads that. A PR shown open or merged adds no line. A wait whose PR has no valid `prStates` row, or rows that disagree, prints an `unknown` line that names the step. With no live file, or a `prStates` that is missing, not a list or empty, one `unknown` line stands for all waits and names no step (`assert_one_unknown_summary` in `skills/roadmap/test_build.py`).
- Wider list: the upkeep row `open step waits on a closed unmerged PR` (`waits_on_closed_pulls` in `skills/roadmap/build.py`) reads `WAIT_ON_PULL_PHRASES`. That list is wider than the guard's words: it adds `stacked on`, `stacks on`, `stack on`, `built on` and `lands with`. This row reads `landedPulls`, not `prStates`.
- The remedy is the step's `blockedBy` slug, or dropping the wait.

Risk kind: likely risk. A session writes "waits on #N" in a step note in normal work. Known limits are filed as notes under step `dead-pr-waits` in `docs/debts/notes.md`.

Kind: process
Home: hooks/guard_merge.py
