# A debt close runs its Retire check

## The ruling

A PR closes a debt when it deletes the debt file, or renames it out of `docs/debts/`. A rename inside that folder is not a close, unless its Retire paragraph changed: then it is a close, and the Retire text at base runs.

- The shared merge tool reads the debt's Retire text at base. It runs each runnable check that text names, in preview and in confirm.
- A runnable check is a backticked path in the Retire text, named like a test file: `test_*.py`, `*_test.py`, `*.test.mjs`, `test_*.mjs` or `test_*.sh`. Its extension sets the runner: `python3`, `node --test` or `bash`. It runs as one argv, with no shell and no model call, under a timeout.
- A Retire names a test file of its own. A shared file proves less.
- A backticked test-named path that head does not track is red.
- Head: the check must pass. A non-zero exit is red. A Python file that runs no test is red: its output says `Ran 0 tests`, or it has `test_` functions and no `__main__` block and exits 0.
- Birth: the check must go red. It runs the head's copy of the test over the tree of the debt's birth commit. The birth commit is the newest commit that added the debt file. A pass there is red: the test does not catch the defect.
  - Python: any non-zero exit is red. It is unknown when the output shows a top-level `ImportError`, `ModuleNotFoundError` or `SyntaxError`, or unittest errors with no failures.
  - Node: red only on `ERR_ASSERTION`. Any other non-zero exit is unknown.
  - Bash: unknown when the output shows a missing file or command, or the exit is 126 or 127. Any other non-zero exit is red.
- A check that cannot run is unknown. A missing interpreter, a failed start, or a timeout also counts. An unknown refuses the close too (decision `ci-unknown-is-red`, an unknown read is red).
- A red check refuses the close. No `Retire-run:` line clears it.
- A cite is a `Retire-run: <slug> -- <text>` line in the PR body. If the text starts with an http(s) URL, it is a run cite. The run must be green on the PR head or on a descendant of it. Text after the URL is ignored.
- Otherwise the text is a reason. A reason clears an unknown only.
- A Retire with no runnable check holds the close, unless a run cite clears it. A reason never closes a prose Retire.

Why: a docs-only PR skips review (decision `docs-only-prs-skip-review`, a docs-only PR gets no full review). So a debt can read as closed while its Retire check never ran. Audit 2026-11-06: 35 debt-delete commits since 2026-10-23, 9 of them markdown-only.

Why the birth commit, not the merge-base: on a markdown-only close the fix already merged, so the merge-base is already green.

Source: coordinator ruling 2026-11-06 13:00 CST (the `Retire-run:` form; a rename out of the folder counts as a close). Coordinator ruling 2026-11-06 13:35 CST (a rename inside the folder with a changed Retire is a close). Coordinator ruling 2026-11-07 15:06 CST (red on the birth commit; a pass there is red; an untracked test path is red; a reason clears an unknown only). Coordinator ruling 2026-11-07 15:39 CST (review finding F1: the run rules match the checker's module docstring). Coordinator ruling 2026-11-07 15:40 CST (a Retire names a test file of its own; a shared file proves less).

Kind: process
Home: lint/check_debt_retire.py
Home: merge/merge.py
Check: lint/check_debt_retire.py
