# A run of zero cases is a failure

## The ruling

A suite run directly must exit 1 when it runs no case. A suite whose cases all skip still exits 0.

- A hand runner with an empty case list prints `<runner> FAIL: no cases ran, so nothing was checked` and exits 1. In `hooks/test_config_watch.py` `main`, `MUTATE_ONLY` filters the cases before the check, so a value that names no case fails the same way (probe: `MUTATE_ONLY=no_such_case_name_zz python3 hooks/test_config_watch.py` prints `test_config_watch FAIL: no cases ran, so nothing was checked`). `run_cases` in `hooks/case_runner_test.py` does the same.
- A skipped case counts as a case that ran. A run of skips exits 0.
- A mods test collector exits 1 when its results list is empty. Its helper never skips: each result is a PASS or a FAIL.
- A `test_*.py` file that defines a TestCase and whose `__main__` block reaches no runner is a problem. `lint/check_suites_have_main.py` reports it.

## The mistake

A suite that loses every case (a filter that matches none, a renamed case list, a missing `unittest.main()` call) or drops its runner's result still exits 0, so its checks read as proven.

- Commit adfab4906a, on `origin/tests-no-real-config`, 2026-11-25 00:03 CST. `lint/test_test_temp.py` and `lint/test_tests_set_config.py` had no `unittest.main()` block. `python3 lint/<file>`, the form `checks.yml` runs, exited 0 with zero cases. The commit adds the block.
- The all-suites audit of 2026-11-24 found the gap across the suites (brief; no tracked record of that audit).

## The harm

CI stays green while a suite tests nothing. CI runs most steps without `bin/verdict`, the one place that fails a run of zero tests.

## What is built

- `no_cases_exit(cases, runner)` in `hooks/case_runner_test.py`. It returns 1 and prints the line when `cases` is empty. A runner calls it first in `main()`.
- The 11 hand runners call it: `hooks/test_agent_brief.py`, `test_config_watch.py`, `test_config_watch_fast_exit.py`, `test_feedback_inbox.py`, `test_guard_load_os.py`, `test_page_link_check.py`, `test_reply_judge.py`, `test_rm_prompt_answer.py`, `test_shared_names.py`, `test_waiting_export.py`, `test_wrappers.py`.
- The four mods collectors fail when their results array is empty (`length === 0`): `mods/token-weather`, `mods/session-board`, `mods/decision-watch`, `mods/plain-diff`.
- `lint/check_suites_have_main.py`, the checker. It reads each `test_*.py` as a syntax tree. A file with a TestCase is clean when a top-level `if __name__ == "__main__":` block reaches `unittest.main` (or a `main` imported from unittest), `run_class` or `TextTestRunner(...).run(...)`. Its reach walk follows a module-level function that the block calls or names. A runner in an `if False:` or `if 0:` body does not count (its `else` does), nor does one outside that block or in an uncalled function. A `run_cases(...)` call that is a bare statement on the `__main__` path is a problem: its dropped count exits 0 on a failure. `ALLOWED` is empty.
- `make_variant` (`lint/test_zero_case_runs.py` `make_variant`) writes the copy of a mods file. Its rewriter (`lint/test_zero_case_runs.py` `REWRITER`) runs under node with TypeScript's scanner, so it changes code and never text.
- `run_class` (`testing/cost_probe.py`) fails a class with no test methods: it prints one line and returns False.
- `hooks/test_local_time.py` `main` exits by the runner's result when no case failed, so a run with no cases exits 1.
- `checks.yml` job `checks` runs four steps: 'Case runner suite', 'Zero-case runs suite', 'Suites have main suite' and 'Suites have main check' (~:352-368).
- Tests: `hooks/test_case_runner.py` (the `CASES` list); `lint/test_zero_case_runs.py` (classes `HandRunnersWithNoCases`, `TokenWeatherCollectorWithNoTests`, `ModsCollectorsWithNoTests` with awaited `test(` calls disabled, `VariantRewriteCases`, `FilterMatchingNoCase`); `lint/test_suites_have_main.py` (classes `FixtureCases`, `RunClassCases`, `RepoRun`).

## Cost

- Checker: one walk of the repo tree, which skips `.git`, `node_modules`, `__pycache__` and `.claude/worktrees`. Then one open and one `ast` parse per `test_*.py`. It writes no file and starts no timer. Run time: unmeasured.
- Zero-case checks: a length test on a list or a results array. No read and no process.
- `lint/test_zero_case_runs.py` starts 12 runner processes: the 11 hand runners in `RUNNERS`, and `hooks/test_config_watch.py` again under `MUTATE_ONLY` (`FilterMatchingNoCase`). It also starts two `node` processes per mods file, and one `node` start per rewriter case (not pinned: no test counts these starts). Each rewrite loads `typescript.js` (size and time unmeasured). Every process has a 300 s limit.

## Limits

- The checker judges per file, not per TestCase class: a file with two classes where `run_class` covers one passes.
- A name reference counts as reached: `print(run)` passes, though `run` never runs.
- Not recognised, so false alarms: `ut.main()` after `import unittest as ut`, and a runner held in a name or a module-level list (`runner = unittest.TextTestRunner()`, then `runner.run(...)`). Only `TextTestRunner(...).run(...)` counts. `ALLOWED` clears a file with a reason.
- An aliased import (`from x import run_cases as rc`) with a bare `rc(...)` call is not flagged: the checker matches the name `run_cases` only.
- The checker reads the syntax tree, not the flow. Only a top-level `__main__` block counts: a `__main__` block nested in an `if` or `try` is not read, so its runner is flagged. A base whose name ends in `TestCase` counts. A TestCase that comes from an imported base with another name is not seen.
- A suite that loses some but not all cases is not caught. A count compare is a later lane.
- The exit-1 check covers the 11 hand runners, the four mods collectors, and the callers of `run_cases` from `hooks/case_runner_test.py`. Of the 49 `hooks/test_*.py` files with no `no_cases_exit` call (`grep -L`, this commit), those callers are guarded by `run_cases`; the rest are not checked.
- `RUNNERS` in `lint/test_zero_case_runs.py` is a hand list. A hand runner not in it is not checked there. The file's own comment names `hooks/test_guard.py` and `lint/check_guardset_lists.py` as left out.
- The copy rewrites only code. It changes an import or export whose specifier starts `./` or `../`, a dynamic `import()` of one, `import.meta.url`, and an awaited `test(...)` statement. It does not change `require(...)`, a specifier without `./` or `../`, or a `test(` call that is not an awaited statement. A run with such a call still exits 1 when its own test fails, so the mods case would pass without a zero-test run.
- `lint/test_zero_case_runs.py` needs `tsc` and `node` on PATH for 11 of its 13 cases, or they skip. The `CI` variable makes them run anyway, so a missing `tsc` fails there. `npm ci --ignore-scripts --prefix actions/code-check/tools` puts `tsc` on PATH (CI does this).
- Not this question: `bin/verdict` fails a zero-test run it reads (PR 3705).

Basis: commit adfab4906a (incident); the all-suites audit of 2026-11-24 (brief).
Kind: process
Home: hooks/case_runner_test.py
