# A run of zero cases is a failure

## The ruling

A suite run directly must exit 1 when it runs no case. A suite whose cases all skip still exits 0.

- A hand runner with an empty case list prints `<runner> FAIL: no cases ran, so nothing was checked` and exits 1. In `hooks/test_config_watch.py` `main`, `MUTATE_ONLY` filters the cases before the check, so a value that names no case fails the same way (probe: `MUTATE_ONLY=no_such_case_name_zz python3 hooks/test_config_watch.py` prints `test_config_watch FAIL: no cases ran, so nothing was checked`). `run_cases` in `hooks/case_runner_test.py` does the same.
- A skipped case counts as a case that ran. A run of skips exits 0.
- A mods test collector exits 1 when its results list is empty. Its helper never skips: each result is a PASS or a FAIL.
- A `test_*.py` file that defines a TestCase and whose `__main__` block reaches no runner is a problem. `lint/check_suites_have_main.py` reports it.

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
- `lint/check_suites_have_main.py`, the checker. It reads each `test_*.py` as a syntax tree. A file with a TestCase is clean when a top-level `if __name__ == "__main__":` block reaches `unittest.main` (or a `main` imported from unittest), `run_class` or `TextTestRunner(...).run(...)`, directly or through a module-level function that block calls. A runner in an `if False:` or `if 0:` body does not count (its `else` does), nor does one outside that block or in an uncalled function. `ALLOWED` is empty.
- `make_variant` (`lint/test_zero_case_runs.py` `make_variant`) writes the copy of a mods file. Its rewriter (`lint/test_zero_case_runs.py` `REWRITER`) runs under node with TypeScript's scanner, so it changes code and never text.
- Tests: `hooks/test_case_runner.py` (3 cases); `lint/test_zero_case_runs.py` (the 11 runners with their case lists emptied; the 4 collectors with every awaited `test(` statement disabled; 7 cases for the copy's code-only edits); `lint/test_suites_have_main.py` (fixture cases `test_suite_without_main_is_a_problem`, `test_suite_with_main_is_clean`, `test_script_without_a_suite_is_clean`, `test_mention_in_string_or_comment_is_clean`, `test_main_only_under_if_false_is_a_problem`, `test_main_in_uncalled_function_is_a_problem`, `test_main_in_function_called_from_guard_is_clean`, `test_text_runner_result_sets_exit_code_is_clean`; repo run `test_repo_has_no_suite_without_main`).

## Cost

- Checker: one walk of the repo tree, which skips `.git`, `node_modules`, `__pycache__` and `.claude/worktrees`. Then one open and one `ast` parse per `test_*.py`. It writes no file and starts no timer. Run time: unmeasured.
- Zero-case checks: a length test on a list or a results array. No read and no process.
- `lint/test_zero_case_runs.py` starts 11 runner processes, two `node` starts per mods file, and one `node` start per rewriter case (not pinned: no test counts these starts). Each rewrite loads `typescript.js` (size and time unmeasured). Every process has a 300 s limit.

## Limits

- No `checks.yml` step runs the checker, `hooks/test_case_runner.py`, `lint/test_suites_have_main.py` or `lint/test_zero_case_runs.py`. CiCoverage (`lint/test_windows_split.py`) flags the three test files for it. On a draft PR, `lane-touched-tests.yml` runs a touched `test_*.py` on Windows. The checker is not a `test_*.py`, so no workflow runs it.
- The exit-1-on-zero check covers the 11 hand runners, the four mods collectors, and the callers of `run_cases`. As of this commit, 49 `hooks/test_*.py` files lack a `no_cases_exit` call (`grep -L`); 5 of those call `run_cases`.
- `RUNNERS` in `lint/test_zero_case_runs.py` is a hand list. A hand runner not in it is not checked there. The file's own comment names `hooks/test_guard.py` and `lint/check_guardset_lists.py` as left out.
- The copy rewrites only code. It changes an import or export whose specifier starts `./` or `../`, a dynamic `import()` of one, `import.meta.url`, and an awaited `test(...)` statement. It does not change `require(...)`, a specifier without `./` or `../`, or a `test(` call that is not an awaited statement. A run with such a call still exits 1 when its own test fails, so the mods case would pass without a zero-test run.
- The mods and rewriter cases need `tsc` and `node` on PATH, or they skip. The `CI` variable makes them run anyway, so a missing `tsc` fails there. `npm ci --ignore-scripts --prefix actions/code-check/tools` puts `tsc` on PATH (CI does this).
- `lint/check_suites_have_main.py` flags a file whose `__main__` block runs a `TextTestRunner` held in a name (`runner = unittest.TextTestRunner()`, then `runner.run(...)`). That is a false alarm: only the direct form `TextTestRunner(...).run(...)` counts. `ALLOWED` clears it with a reason.
- The checker reads the syntax tree, not the flow. Only a top-level `__main__` block counts: a `__main__` block nested in an `if` or `try` is not read, so its runner is flagged. A base whose name ends in `TestCase` counts. A TestCase that comes from an imported base with another name is not seen.
- Not this question: `bin/verdict` fails a zero-test run it reads (PR 3705). That record answers when verdict reads an exit-0 run as a failure. Its record, `decisions/verdict-reads-runner-markers.md`, was culled in commit 46eaf546d5.

Basis: commit adfab4906a (incident); the all-suites audit of 2026-11-24 (brief).
Kind: process
Home: hooks/case_runner_test.py
