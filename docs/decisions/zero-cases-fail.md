# A run of zero cases is a failure

## The ruling

A suite run directly must exit 1 when it runs no case. A suite whose cases all skip still exits 0.

- A hand runner with an empty case list prints `<runner> FAIL: no cases ran, so nothing was checked` and exits 1. The check runs before any filter. `run_cases` in `hooks/case_runner_test.py` does the same.
- A skipped case counts as a case that ran. A run of skips exits 0.
- A mods test collector exits 1 when its results list is empty. Its helper never skips: each result is a PASS or a FAIL.
- A `test_*.py` file that defines a TestCase and calls neither `unittest.main` nor `run_class` is a problem. `lint/check_suites_have_main.py` reports it.

## The mistake

A suite can lose every case and still exit 0 when run directly. The causes are a filter that matches no case, a renamed case list, or a missing `unittest.main()` call.

- Commit adfab4906a, on `origin/tests-no-real-config`, 2026-11-25 00:03 CST. `lint/test_test_temp.py` and `lint/test_tests_set_config.py` had no `unittest.main()` block. `python3 lint/<file>`, the form `checks.yml` runs, exited 0 with zero cases. The commit adds the block.
- The all-suites audit of 2026-11-24 found the gap across the suites (brief; no tracked record of that audit).

## The harm

CI stays green while a suite tests nothing. CI runs most steps without `bin/verdict`, the one place that fails a run of zero tests.

## What is built

- `no_cases_exit(cases, runner)` in `hooks/case_runner_test.py`. It returns 1 and prints the line when `cases` is empty. A runner calls it first in `main()`.
- The 11 hand runners call it: `hooks/test_agent_brief.py`, `test_config_watch.py`, `test_config_watch_fast_exit.py`, `test_feedback_inbox.py`, `test_guard_load_os.py`, `test_page_link_check.py`, `test_reply_judge.py`, `test_rm_prompt_answer.py`, `test_shared_names.py`, `test_waiting_export.py`, `test_wrappers.py`.
- The four mods collectors fail on `results.length === 0`: `mods/token-weather`, `mods/session-board`, `mods/decision-watch`, `mods/plain-diff`.
- `lint/check_suites_have_main.py`, the checker. It reads each `test_*.py` as a syntax tree. `ALLOWED` is empty.
- Tests: `hooks/test_case_runner.py` (3 cases); `lint/test_zero_case_runs.py` (the 11 runners with their case lists emptied, and the 4 collectors with every `await test(` disabled); `lint/test_suites_have_main.py` (4 fixture cases and 1 run over the repo).

## Cost

- Checker: one walk of the repo tree, which skips `.git`, `node_modules`, `__pycache__` and `.claude/worktrees`. Then one open and one `ast` parse per `test_*.py`. It writes no file and starts no timer. Run time: unmeasured.
- Zero-case checks: a length test on a list or a results array. No read and no process.
- `lint/test_zero_case_runs.py` starts 11 runner processes and up to 4 `node` processes per run, each with a 300 s limit. Run time: unmeasured.

## Limits

- No `checks.yml` step runs the checker, `hooks/test_case_runner.py`, `lint/test_suites_have_main.py` or `lint/test_zero_case_runs.py`. On a draft PR, `lane-touched-tests.yml` runs a touched `test_*.py` on Windows. The checker is not a `test_*.py`, so no workflow runs it.
- A filter after the check. In `hooks/test_config_watch.py`, `MUTATE_ONLY` filters the case loop in `main()` after `no_cases_exit`. A value that names no case runs zero cases, skips the sweep check, prints `PASS: N of N cases right` and exits 0. `no_cases_exit` does not catch this.
- `RUNNERS` in `lint/test_zero_case_runs.py` is a hand list. A hand runner not in it is not checked there. The file's own comment names `hooks/test_guard.py` and `lint/check_guardset_lists.py` as left out.
- `STATIC_IMPORT` in `lint/test_zero_case_runs.py` is a text match, not a parse. It matches `from `, `import ` or `import(`, then a `'` or `"` quote, then a specifier that starts `./` or `../`, up to the same quote. It matches inside strings and comments too. It misses backtick specifiers, `require(...)`, and `import (` with a space. In the same copy step, `zero_test_exit` replaces every `import.meta.url` and every `await test(` as plain text.
- The checker reads the syntax tree, not the flow. A `unittest.main()` or `run_class` call anywhere in the file counts, even under `if False` or in an uncalled function. A base whose name ends in `TestCase` counts. A TestCase that comes from an imported base with another name is not seen.
- `lint/test_zero_case_runs.py` skips its four mods cases when `node` is not on PATH.
- Not this question: `bin/verdict` fails a zero-test run it reads (PR 3705). That record answers when verdict reads an exit-0 run as a failure. Its record, `decisions/verdict-reads-runner-markers.md`, was culled in commit 46eaf546d5.

Basis: commit adfab4906a (incident); the all-suites audit of 2026-11-24 (brief).
Kind: process
Home: hooks/case_runner_test.py
