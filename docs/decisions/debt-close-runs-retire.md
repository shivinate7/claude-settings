# A debt close runs its Retire check

## The ruling

A PR closes a debt when it deletes the debt file, or renames it out of `docs/debts/`. A rename inside that folder is not a close, unless its Retire paragraph changed: then it is a close, and the Retire text at base runs.

- The shared merge tool reads the debt's Retire text at base. It runs each runnable check that text names, in preview and in confirm.
- A runnable check is a backticked path in the Retire text, named like a test file: `test_*.py`, `*_test.py`, `*.test.mjs`, `test_*.mjs` or `test_*.sh`. Its extension sets the runner: `python3`, `node --test` or `bash`. No shell, no model call.
- A backticked test-named path that head does not track is red.
- Each runnable check runs on two trees:
  - The PR head. The check must pass.
  - The debt's birth commit, the commit that added the debt file, with head's test files laid over that tree. The check must go red. A pass there counts as red: the test does not catch the defect.
- Red on the birth commit must be a test failure. An import or collection error, or errors with no failures, is unknown.
- A check that cannot run is unknown. An unknown refuses the close too (decision `ci-unknown-is-red`, an unknown read is red).
- A red check refuses the close. No `Retire-run:` line clears it.
- An unknown clears only with one of these lines in the PR body:
  - `Retire-run: <slug> -- <run URL>`, for a green run on the PR head or on a descendant of it.
  - `Retire-run: <slug> -- <reason>`, for a written reason.
- A PR with no runnable check is refused. Only `Retire-run: <slug> -- <run URL>` clears it. A reason never clears it.

Why: a docs-only PR skips review (decision `docs-only-prs-skip-review`, a docs-only PR gets no full review). So a debt can read as closed while its Retire check never ran. Audit 2026-11-06: 35 debt-delete commits since 2026-10-23, 9 of them markdown-only.

Why the birth commit, not the merge-base: on a markdown-only close the fix already merged, so the merge-base is already green.

Source: coordinator ruling 2026-11-06 13:00 CST (the `Retire-run:` form; a rename out of the folder counts as a close). Coordinator ruling 2026-11-06 13:35 CST (a rename inside the folder with a changed Retire is a close). Coordinator ruling 2026-11-07 15:06 CST (red on the birth commit; a pass there is red; an untracked test path is red; a reason clears an unknown only).

Kind: process
Home: lint/check_debt_retire.py
Home: merge/merge.py
Check: lint/check_debt_retire.py
