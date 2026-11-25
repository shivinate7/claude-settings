# Each test case's time is kept, and a far-slow case is flagged

## The ruling

Question: how does the repo know what each test case costs?

Owner, 2026-11-24 21:19 CST, typed in chat: "cases can be uneven sized -- is there any reason not to just keep the clock on all of them? some may be justifiably long others not so? ie a 20s test that shd take .5s will never be found if we do this route"

Reading: time every case, and keep every time.

## The mistake and the harm

A suite total hides a slow case, and so does a slowest-25 list. A case that should take 0.5 s and takes 20 s sits inside its suite's total. Behind cases that are long for good reason, it can fall outside the list. Nobody can see which case to cut.

## What is built

- Recording arms only when env `CASE_TIMES=1` and `RUNNER_TEMP` is set. `testing/case_times/sitecustomize.py` arms a process at its start when its folder is on `PYTHONPATH`. Unarmed, it writes nothing.
- A row has `suite`, `group`, `case`, `s`, `fixture_s` and `outcome` (`pass`, `fail` or `skip`). Each armed process holds its rows in memory and appends them once, at exit, to `RUNNER_TEMP/case-times/<GITHUB_JOB>.jsonl` (`local` when no job name is set). A process with no rows writes no file.
- unittest: one row per test method, timed from its start to its stop. A method's subTests make one row. `group` is the suite. `fixture_s` is 0.0 on these rows.
- Guard runner (`hooks/test_guard.py`): one row per case and per log check. `suite` is `hooks/test_guard.py`, `group` is the case's family, and a log check's `case` starts with `log: `. `fixture_s` is the time of lazy fixture blocks, taken out of `s`.
- Child processes write no rows. Mutation runs drop `CASE_TIMES` from their environment (`hooks/mutate_shared.py`, `run_suite_file`). An armed process drops it when `unittest.result` loads, so later children start unarmed.
- Reader: `lint/case_times_report.py [--dir FOLDER]`, default `RUNNER_TEMP/case-times`. It merges every job file and groups rows by suite and group. Skipped rows are left out of the median. A case is flagged at 10 times its group's median and at least 1.0 s, in groups of 5 or more. A missing, empty or bad folder prints `unknown`. It always exits 0 and gates nothing.
- Known false flag: a module-level fixture that a unittest file builds lazily in its first case lands on that case, which can be flagged.

## What it costs

Cost (rule `outcomes-mechanize-rules`): the recording runs only in armed Python processes, and the reader runs only when called.

- Process starts: none.
- Files written: one per armed job. Each armed process that has rows appends to it once, at exit.
- How often: only in an armed run. An unarmed Python start costs one import and writes no file.
- Reader: on demand. It writes no file.

Check: `lint/test_case_times.py`: `Cost.test_no_child_and_one_file`, `Cost.test_unarmed_child_one_import_no_file`, `Unarmed.test_no_env_writes_no_file`, `Unarmed.test_no_unittest_import_writes_no_file`, `Children.test_suite_child_writes_no_row`, `Children.test_mutation_child_writes_no_row`, `Records.test_one_row_per_case_with_outcome`, `GuardRows.test_one_row_per_case_fixture_netted`, `Chain.test_next_sitecustomize_still_runs`. `lint/test_case_times_report.py`: `Flags.test_ten_times_median_over_floor_flagged`, `Flags.test_under_floor_not_flagged`, `Flags.test_small_group_not_judged`, `Flags.test_bad_file_unknown_exit_zero`.

## Consultant picks

Picks by the consultant. The owner may reverse any of them.

- Times kept 14 days. The retention is not set yet (see Not built).
- Flags on demand only: no watcher, no timer.
- Thresholds: 10 times the group median, and 1.0 s. Groups of 5 or more.
- Log checks get rows too.

## Not built

- The CI workflow hunk. It sets `CASE_TIMES=1`, `RUNNER_TEMP` and `PYTHONPATH` for the jobs, and uploads the job files. It waits on the open PRs that hold the workflow. Until it lands, nothing arms the recording in CI.
- The 14-day retention. It is a workflow setting, not yet set.
- The two lint test files run in no CI step.

## Unmeasured

- Armed against unarmed time: one sample. 1.19 s armed, 0.69 s unarmed, on a 6-case suite. Noise is not ruled out.
- Python 3.9: checked by a syntax parse only. Not run.

State: decided. Built: the recording, the reader and their tests. Not built: the CI arming.

Kind: process
Home: testing/case_times/case_times.py
