# A debt close runs its Retire check

## The ruling

A PR closes a debt when it deletes the debt file, or renames it out of `docs/debts/`. A rename inside that folder is not a close, unless its Retire paragraph changed: then it is a close, and the Retire text at base runs.

- The shared merge tool reads the debt's Retire text at base. It runs each runnable check that text names, on the PR head, in preview and in confirm.
- A red check refuses the close. A check that cannot run refuses it too (decision `ci-unknown-is-red`, an unknown read is red).
- A PR with no runnable check is refused. The way out, for no runnable check or one that cannot run: the PR body holds `Retire-run: <slug> -- <run URL>`, for a run that succeeded on the PR head or on a descendant of it. A cite never clears a red check.
- A runnable check is a backticked path in the Retire text. The path is tracked at head and named like a test file: `test_*.py`, `*_test.py`, `*.test.mjs`, `test_*.mjs` or `test_*.sh`. Its extension sets the runner: `python3`, `node --test` or `bash`. No shell, no model call.

Why: a docs-only PR skips review (decision `docs-only-prs-skip-review`, a docs-only PR gets no full review). So a debt can read as closed while its Retire check never ran. Audit 2026-11-06: 35 debt-delete commits since 2026-10-23, 9 of them markdown-only.

Source: coordinator ruling 2026-11-06 13:00 CST (the `Retire-run:` form; a rename out of the folder counts as a close). Coordinator ruling 2026-11-06 13:35 CST (a rename inside the folder with a changed Retire is a close).

Kind: process
Home: lint/check_debt_retire.py
Home: merge/merge.py
Home: lint/check_silent_undo.py
Check: lint/check_debt_retire.py
