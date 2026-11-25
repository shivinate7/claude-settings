# A ready pull request runs marked Windows tests in its guard and merge slices

## The ruling

Question: which Windows tests does a ready pull request run?

Ruling: owner, 2026-11-24 21:19 CST, on "a ready PR runs only Windows-marked tests, full Windows suites daily": "approved with B done afterwards". B is an audit that marks every test that touches a Windows-only branch.

Ruling: owner, 2026-11-24 22:27 CST, on landing the cut before the fix that keeps a red daily visible: "that's fine, no work is currently occuring on windows, and the time savings would come now".

Consultant's pick, not owner-typed, no time recorded; the owner may reverse it: the slice steps sit inside the two base Windows jobs, and no new job is added.

## Reading of the ruling

The owner's words (21:19 CST Nov 24 2026) are "a ready PR runs only Windows-marked tests". This cut applies them to the guard and merge shards, where the measured time is. Five of the six flag-gated Windows jobs keep their full suite when a PR touches the files they test. In the sixth, `checks-windows-merge`, only its two launcher steps run whole; its git-half suite runs as the slice. That narrower reading is the consultant's pick (23:35 CST Nov 24 2026, undoable). It departs from the plain words. The owner has not confirmed it.

## What runs now

- A ready pull request starts 7 Windows jobs. It started 20 before this cut. The 7 are `checks-windows`, `pointer-windows`, `checks-windows-guard`, `checks-windows-merge`, `checks-windows-rest`, `checks-windows-rest-2` and `checks-windows-sweep`.
- On a ready pull request, base job `checks-windows-guard` runs the step "Guard fixture suite (Windows slice)", with `GUARD_TESTS=windows-slice`. It needs the scope flag `windows_guard`.
- On a ready pull request, base job `checks-windows-merge` runs the step "Merge tool git-half fixture suite (Windows slice)", with `MERGE_TESTS=windows-slice`. It needs the scope flag `checks_windows_merge`.
- The slice runs only the tests marked for Windows. On a schedule or a dispatch, those two jobs run their shard 1 step instead: "Guard fixture suite (shard 1 of 5)" and "Merge tool git-half fixture suite (shard 1 of 10)".
- Six flag-gated Windows jobs run their full suite on a ready pull request when their scope flag is set, that is, when the pull request touches files they test: `pointer-windows`, `checks-windows`, `checks-windows-sweep`, `checks-windows-rest`, `checks-windows-rest-2`, and `checks-windows-merge` for its two launcher steps, "Merge launcher fixture suite" and "Merge launcher fixture suite (merge.cmd)".
- The 13 full shard jobs, `checks-windows-guard-2` to `-5` and `checks-windows-merge-2` to `-10`, run on the daily schedule and on manual dispatch only. They are not in the `needs` of `all-jobs-passed`. `ci-done` still needs them.

## The cost removed

- Measure: Windows was 62.8% of job-seconds on run 45526976959. Each Windows shard ran 956 to 1,396 s on that run. The lane read these figures; they were not re-read for this record.
- Unmeasured: the slice steps' own time. The lane's first PR run measures it.

## The accepted risk

A Windows-only break in an unmarked guard or merge test now reaches main. A ready pull request does not run that test. The break first shows at the daily run.

## What narrows it

- The daily run runs every Windows shard, marked and unmarked tests alike.
- Each ready pull request runs every Windows-marked test in the guard and merge slices.

## What does not narrow it yet

- The marking audit judged 130 cases: 67 guard, 59 merge, and 4 merge-skip-by-nature cases marked today. It did not judge 638 more: 261 guard and 377 merge. Count: `grep -v '^#' claude-settings-windows-unmarked-cases.tsv | cut -f1,6 | sort | uniq -c`, run on the audit file, which sits outside this repo. The slice stays incomplete until the marking build lands. Debt `windows-slice-marks-incomplete`.
- Only 51 of 1,356 guard log checks can carry the Windows flag today. The flag comes from the hand list `WINDOWS_CHECKERS`. The audit gave these counts; they were not re-read for this record.
- A red daily on a Windows shard that left the rollup is not shown to the next merge until the follow-up lane `red-main-reads-back-to-daily` lands. The 22:27 CST ruling put this cut first. Debt `red-daily-not-yet-visible`.

## Departs from

- The plain words of the 21:19 CST Nov 24 ruling. Five flag-gated Windows jobs still run whole on a ready PR that touches their files. The merge job's two launcher steps also run whole.
- Decision `ci-cut-in-steps`, rule R4a, as it stood on main: Windows shards on a pull request ran under their scope flag. Now the 13 shard jobs do not run on a pull request.
- The full Windows shards on a ready pull request, from roadmap step R62. Its record lives on the roadmap branch, not on main.

Kind: process
Home: .github/workflows/checks.yml
