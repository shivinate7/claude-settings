# Each test case's time is kept, and a far-slow case is flagged

## The ruling

Question: how does the repo know what each test case costs?

Owner, 2026-11-24 21:19 CST, typed in chat: "cases can be uneven sized -- is there any reason not to just keep the clock on all of them? some may be justifiably long others not so? ie a 20s test that shd take .5s will never be found if we do this route"

Reading: time every case, and keep every time.

## The mistake and the harm

A suite total hides a slow case, and so does a slowest-25 list. A case that should take 0.5 s and takes 20 s sits inside its suite's total. Behind cases that are long for good reason, it can fall outside the list. Nobody can see which case to cut.

## What is built

- Recording arms only when env `CASE_TIMES=1` and `RUNNER_TEMP` is set. `testing/case_times/sitecustomize.py` arms a process at its start when its folder is on `PYTHONPATH`. Unarmed, it writes nothing.
- A row has `suite`, `group`, `case`, `s`, `fixture_s` and `outcome` (`pass`, `fail` or `skip`). `s` is the case's own seconds. `fixture_s` is the seconds of its setUp and tearDown (and, for an IsolatedAsyncioTestCase, of its asyncSetUp and asyncTearDown), apart from `s`. Each armed process holds its rows in memory and appends them once, at exit, to `RUNNER_TEMP/case-times/<GITHUB_JOB>.jsonl` (`local` when no job name is set). A process with no rows writes no file.
- unittest: one row per test method, timed from its start to its stop. A method's subTests make one row. `group` is the suite. setUp and tearDown are timed by wrapping unittest's private `_callSetUp` and `_callTearDown` on TestCase. When `unittest.async_case` loads, the same wrap goes on IsolatedAsyncioTestCase, so its asyncSetUp and asyncTearDown seconds are fixture time too. The arm itself imports no asyncio (see Limits).
- A case that starts inside another open case gets no row. The outer case's row holds that time.
- A frame that a case leaves open is dropped when the case it sits under stops. That stop writes one `case_times:` stderr line that names the dropped case. The case it sits under keeps its row, and later cases keep theirs.
- An import failure is named for the failed module's file when that file is in the cwd latched at arm time, else `import-failure`.
- A row that cannot be kept writes one stderr line and changes no result.
- A class whose `_callSetUp` or `_callTearDown` cannot be read (a Python that renamed one) runs both calls unwrapped. Its cases still run, their setUp and tearDown seconds stay in `s`, and one `case_times:` stderr line says so.
- `case_times.py` sets `__unittest = True`, so unittest leaves its frames out of a traceback. An armed setUp error prints the same traceback as an unarmed one.
- Two copies of the home on `PYTHONPATH` do not recurse.
- Guard runner (`hooks/test_guard.py`): one row per case and per log check. `suite` is `hooks/test_guard.py`, `group` is the case's family, and a log check's `case` starts with `log: `. `fixture_s` is the time of lazy fixture blocks, taken out of `s`.
- Children: an armed process drops `CASE_TIMES` when `unittest.result` loads, so a child it starts after that writes no rows. Mutation runs drop it too, since their runner imports no unittest (`hooks/mutate_shared.py`, `run_suite_file`).
- Reader: `lint/case_times_report.py [--dir FOLDER]`, default `RUNNER_TEMP/case-times`. It prints `read: <path>` for each job file it reads, and `missing: <job>` for each job named in env `CASE_TIMES_JOBS` with no file. It merges every job file and groups rows by suite and group. Skipped rows stay out of every group. A case's time is `s` plus `fixture_s`. A case is flagged at 10 times its group's median of that time, and at least 1.0 s, in groups of 5 or more. A missing, empty or bad folder prints `unknown`. It exits 0 after any read and gates nothing.
- Known false flag: a module-level fixture that a unittest file builds lazily in its first case lands on that case, which can be flagged.

## What it costs

Cost (rule `outcomes-mechanize-rules`): the recording runs only in armed Python processes, and the reader runs only when called.

- Process starts: none. The import finder watches one more module name, `unittest.async_case`. That adds no start and no file.
- Files written: one per armed job. Each armed process that has rows appends to it once, at exit.
- How often: only in an armed run. An unarmed Python start costs one import and writes no file.
- Reader: on demand. It writes no file.

Check: `lint/test_case_times.py`: `Cost.test_no_child_and_one_file`, `Cost.test_unarmed_child_one_import_no_file`, `Unarmed.test_no_env_writes_no_file`, `Unarmed.test_no_unittest_import_writes_no_file`, `Children.test_suite_child_writes_no_row`, `Children.test_mutation_child_writes_no_row`, `Records.test_one_row_per_case_with_outcome`, `GuardRows.test_one_row_per_case_fixture_netted`, `Chain.test_next_sitecustomize_still_runs`. `lint/test_case_times_report.py`: `Flags.test_ten_times_median_over_floor_flagged`, `Flags.test_under_floor_not_flagged`, `Flags.test_small_group_not_judged`, `Flags.test_bad_file_unknown_exit_zero`.

Checks for the facts above: `lint/test_case_times.py`: `FixtureTime.test_setup_and_teardown_land_in_fixture_s`, `NestedRuns.test_inner_case_keeps_no_row_of_its_own`, `ImportFailure.test_named_by_the_failed_modules_own_file`, `ImportFailure.test_no_file_is_named_import_failure`, `TwoHomes.test_two_copies_of_the_home_chain_once`, `RowFails.test_a_row_that_cannot_be_kept_writes_one_stderr_line`, `OpenFrame.test_open_frame_at_flush_keeps_later_rows_and_names_it`, `ArmWithoutCallSetUp.test_missing_call_setup_still_starts_and_runs`, `AsyncFixture.test_async_setup_seconds_land_in_fixture_s`, `SetupTraceback.test_setup_error_traceback_matches_unarmed`. `lint/test_case_times_report.py`: `JobFiles.test_prints_each_job_file_read`, `JobFiles.test_named_job_without_a_file_is_listed_missing`, `Literal.test_fixture_time_counts_toward_the_flag`, `Literal.test_skipped_rows_left_out_of_the_median`.

## Consultant picks

Picks by the consultant. The owner may reverse any of them.

- Times kept 14 days. The retention is not set yet (see Not built).
- Flags on demand only: no watcher, no timer.
- Thresholds: 10 times the group median, and 1.0 s. Groups of 5 or more.
- The flag reads `s` plus `fixture_s`, the case's whole time, from the owner's ask above (consultant, 23:39 CST Nov 24 2026; undoable).
- Log checks get rows too.

## Not built

- The CI workflow hunk. It sets `CASE_TIMES=1`, `RUNNER_TEMP` and `PYTHONPATH` for the jobs, and uploads the job files. It waits on the open PRs that hold the workflow. Until it lands, no CI job sets `CASE_TIMES=1`.
- The 14-day retention. It is a workflow setting, not yet set.
- The two lint test files run in CI only when a PR touches them (`.github/workflows/lane-touched-tests.yml`).

## Limits

- 35% of test files (hand, node, shell and PowerShell runners) get no row. Counted 2026-11-24: about 87 of 246.
- Private unittest methods (`_callSetUp`, `_callTearDown`) carry the fixture timing, on TestCase and IsolatedAsyncioTestCase. Checked on Python 3.15.2 and 3.12.14. Python 3.9 is unmeasured (see Unmeasured).
- Matrix legs share `GITHUB_JOB`, so their job files would collide. Open: no fix yet.

## Unmeasured

- Armed against unarmed time: one sample. 1.19 s armed, 0.69 s unarmed, on a 6-case suite. Noise is not ruled out.
- Python 3.9: unmeasured. Not run.

State: decided. Built: the recording, the reader and their tests. Not built: the CI arming.

Kind: process
Home: testing/case_times/case_times.py
