# The mutation report scores suites, on demand

## The ruling

`hooks/mutate_guard.py --report` scores the suites of other verdict-deciding files with mechanical mutants, on demand. It answers the owner's question: do the tests pin anything that matters, or a static result? It is the report mode of the one home of mutation testing (`hooks/mutate_guard.py` with `hooks/mutate_shared.py`). It is not a second tool.

The mode makes mutants of a target file mechanically, with the `ast` module. It flips a comparison, swaps `and` with `or`, drops a `not`, and swaps `True` with `False`. It negates an `if` or `while` test, sets a return value to `None`, and drops a `return`. It samples 10 mutants per file, the same 10 on every run (seed 0). It runs each suite that names the file, in a copy of the repository, against each mutant. It prints, per file: mutants made, killed, crashed, survived, the kill rate, and the suites that killed no mutant. `REPORT_TARGETS` in `hooks/mutate_guard.py` lists the files and their suites. A new verdict-deciding file joins the report by one line there.

Two counts are held shut:

- A crash is not a kill. A mutant is killed only when a suite prints a `FAIL` line. A throw, an import error and a timeout leave no `FAIL` line, or end at the timeout, so they count as crashed.
- A suite that is not green on the clean source is not a killer. Each suite first runs on the clean source after the same parse and unparse that every mutant carries. A suite that is red there is listed as unusable for that file. A file with no usable suite, a parse error or a missing target reads UNKNOWN, never a rate.

A target in JavaScript or TypeScript gets the same kinds of mutant from `hooks/mutate_js.mjs`, run by `js_mutants` in `hooks/mutate_shared.py`. The engine parses with the TypeScript compiler API, loaded only through the plain-english-map loader (`lazy-typescript.mjs`, the one home of that import). It reads sites from the parse tree. A string, a template literal, a comment or JSX text that holds `a === b` gets no mutant. Each mutant is one text edit on the original source, and nothing else is reprinted. `js_mutants` samples as `ast_mutants` does. `classify_node_tap` reads a `node --test` run as `classify_run` reads a Python suite: only an assertion in a `not ok` block is a kill, and any other red is a crash.

Both engines take a `lines` filter. `changed_lines` lists the lines that a commit range adds to a file, so a run can mutate only the code a change touched.

The report refuses nothing. No timer starts it, it starts no long-lived process, and it is not a required CI job. `hooks/test_mutate_report.py` pins the two counts (fixture suites that pin nothing, catch a mutant, crash, are red on the clean source, and an unrunnable file). `hooks/test_mutate_js.py` pins the JS engine, the filter and the TAP classes.

## The scores

One run, 10 mutants per file, 3 suites at a time. The gold standard is the guard's own kill rate: `python3 hooks/mutate_guard.py` killed 367 of 367 hand-written mutations (0 survived, 0 wrong cause), each one tied to a named required case. The same ast engine on `hooks/guard_wsl.py` with `hooks/test_guard.py` read UNKNOWN: that suite is not green on the clean, unparsed source. So the gold is the hand-written rate, and the ast rates below are not held against it on equal terms.

| File | Mutants | Killed | Crashed | Survived | Rate | Gold |
|---|---|---|---|---|---|---|
| `hooks/guard*.py`, hand-written (gold) | 367 | 367 | 0 | 0 | 100% | 100% |
| `lint/report_guard.py` | 10 | 6 | 3 | 1 | 60% | 100% |
| `hooks/feedback_guard.py` | 10 | 9 | 0 | 1 | 90% | 100% |
| `hooks/stall_watch.py` | 10 | 6 | 1 | 3 | 60% | 100% |
| `lint/check_silent_undo.py` | 10 | 6 | 0 | 4 | 60% | 100% |
| `hooks/guard_wsl.py` (same engine) | UNKNOWN | | | | UNKNOWN | |

Suites that killed none of the 10 mutants of their file. None is un-run or unread: each runs in CI and goes red on a planted failure (record `c197-silent-tests`). They test other things, so the report's attribution of them to these files is a misattribution, not a gap:

- `lint/report_guard.py`: `hooks/test_reply_judge.py`, `hooks/test_wrappers.py`, `lint/test_rule_audit.py`, `lint/test_settings_matcher.py`. Only `lint/test_report_guard.py` kills.
- `hooks/feedback_guard.py`: `lint/test_settings_matcher.py`. Only `hooks/test_feedback_inbox.py` kills.
- `hooks/stall_watch.py`: `hooks/test_wrappers.py`, `lint/test_hook_platform_exit.py`, `janitor/test_session_end_sweep.py`, `lint/test_settings_matcher.py`. The two `hooks/test_stall_watch*.py` suites kill.
- `lint/check_silent_undo.py`: none. Its one suite kills.

How to read it. A review probe broke each file wholly. Every silent suite except `hooks/test_reply_judge.py` stayed green, so those suites do not test the file's logic at all: they name it in a list (a hook registered, a platform exit, a wrapper shape). `hooks/test_reply_judge.py` went red, so it loads `lint/report_guard.py` and only missed the sample. The mode itself does not prove a silent suite loaded the mutant. A mutant that throws in a child process that the suite reports as a FAIL line counts as killed, so each rate is an upper bound. The verdict logic of each file is pinned by its own suite. So the measure does not show a worthless suite. It shows that nothing except the file's own suite guards the verdict. A survivor may be an equivalent mutant (no change in behaviour), which the mode cannot tell from a gap. A sample of 10 gives a coarse rate: read 60% as "a gap exists", not as an exact figure. A suite silent on 10 mutants may still catch one outside the sample.

Not measured (UNKNOWN): `hooks/test_guard.py`, `merge/test_merge.py` and `lint/test_ci_scope.py` against these files. The first two take minutes for each mutant. The third only passes a file path to the scope detector.

## Cost

One full report run, measured: 41.5 minutes on 4 cores with `--jobs 3`. About 155 suite process starts and 5 `git init` starts. The slowest suite, `hooks/test_stall_watch.py`, takes 150 s a run. The JS engine adds one `node` start per file mutated. Files written: temporary copies of the repository (about 13 MB each; the clean copy and up to 3 mutant copies at a time) in the system temp folder, all removed at the end. Nothing is written to the repository. `--limit N` and `--only TEXT` bound a run. A run stopped before its end keeps the rows already printed, because each file's row prints as that file ends.

Kind: process
Home: hooks/mutate_shared.py
