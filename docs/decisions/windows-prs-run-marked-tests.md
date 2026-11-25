# A ready pull request runs only the Windows-marked tests

## The ruling

Question: which Windows tests does a ready pull request run?

Ruling: owner, 2026-11-24 21:19 CST, on "a ready PR runs only Windows-marked tests, full Windows suites daily": "approved with B done afterwards". B is an audit that marks every test that touches a Windows-only branch.

Ruling: owner, 2026-11-24 22:27 CST, on landing the cut before the fix that keeps a red daily visible: "that's fine, no work is currently occuring on windows, and the time savings would come now".

Consultant's pick, not owner-typed, no time recorded; the owner may reverse it: the slice steps sit inside the two base Windows jobs, and no new job is added.

## What runs now

- A ready pull request starts 7 Windows jobs. It started 20 before this cut. The 7 are `checks-windows`, `pointer-windows`, `checks-windows-guard`, `checks-windows-merge`, `checks-windows-rest`, `checks-windows-rest-2` and `checks-windows-sweep`.
- Base job `checks-windows-guard` runs the step "Guard fixture suite (Windows slice)" on a pull request, with `GUARD_TESTS=windows-slice`. It needs the scope flag `windows_guard`.
- Base job `checks-windows-merge` runs the step "Merge tool git-half fixture suite (Windows slice)", with `MERGE_TESTS=windows-slice`. It needs the scope flag `checks_windows_merge`.
- The slice runs only the tests marked for Windows. Each base job runs its full step on every other event it starts on.
- The 13 full shard jobs, `checks-windows-guard-2` to `-5` and `checks-windows-merge-2` to `-10`, run on the daily schedule and on manual dispatch only. They are not in the `needs` of `all-jobs-passed`. `ci-done` still needs them.

## The cost removed

- Measure: Windows was 62.8% of job-seconds on run 45526976959. Each Windows shard ran 956 to 1,396 s on that run. The lane read these figures; they were not re-read for this record.
- Unmeasured: the slice steps' own time. The lane's first PR run measures it.

## The accepted risk

A Windows-only break in an unmarked test now reaches main. A ready pull request does not run that test. The break first shows at the daily run.

## What narrows it

- The daily run runs every Windows shard, marked and unmarked tests alike.
- Each ready pull request runs every Windows-marked test in its base jobs.

## What does not narrow it yet

- The marking audit found 45 merge cases and 85 guard cases that need a Windows mark. That is 130 cases. It did not judge 638 more. The slice stays incomplete until the marking build lands. Debt `windows-slice-marks-incomplete`.
- Only 51 of 1,356 guard log checks can carry the Windows flag today. The flag comes from the hand list `WINDOWS_CHECKERS`. The audit gave these counts; they were not re-read for this record.
- A red daily on a Windows shard that left the rollup is not shown to the next merge until the follow-up lane `red-main-reads-back-to-daily` lands. The 22:27 CST ruling put this cut first. Debt `red-daily-not-yet-visible`.

## Departs from

- Decision `ci-cut-in-steps`, rule R4a. That rule has Windows shards on a pull request run with their scope flag. Now the 13 shard jobs do not run on a pull request.
- The full Windows shards on a ready pull request, from roadmap step R62. Its record lives on the roadmap branch, not on main.

Kind: process
Home: .github/workflows/checks.yml
