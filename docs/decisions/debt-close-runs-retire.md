# A debt close runs its Retire check

## The ruling

A PR closes a debt when it deletes the debt file, or renames it out of `docs/debts/`. A rename inside that folder is not a close, unless its Retire paragraph changed: then it is a close, and the Retire text at base runs.

- CI runs the check on every pull request (the `Debt retire check` step in `checks.yml`). It reads the debt's Retire text at base and runs each runnable check that text names, on the PR head. It reads the PR body from the event file, and a cited run through `gh` with the job's token. The merge tool reads CI's verdict. Confirm runs no Retire check: its checks wait reads CI's verdict on the head. Preview runs the check only when the head's CI does not read green (red, pending or unknown), so it names the finding. Outside CI the CLI has no PR body, so a close that needs a cite reads unknown, never prose. The merge tool and the CLI share one reader of a cited run (`run_route`, `parse_run` in `lint/check_debt_retire.py`).
- A red check refuses the close. A check that cannot run refuses it too (decision `ci-unknown-is-red`, an unknown read is red).
- A PR with no runnable check is refused. The way out, for no runnable check or one that cannot run: the PR body holds `Retire-run: <slug> -- <run URL>`, for a run that succeeded on the PR head or on a descendant of it. A cite never clears a red check.
- A runnable check is a backticked path in the Retire text. The path is tracked at head and named like a test file: `test_*.py`, `*_test.py`, `*.test.mjs`, `test_*.mjs` or `test_*.sh`. Its extension sets the runner: `python3`, `node --test` or `bash`. No shell, no model call.
- An isolated run (the merge tool, the CLI) links installed `node_modules` into the scratch worktree, at the root and beside each tracked `package.json`. Each folder comes from the checkout the check reads when it has one, else from the main checkout of that repository. The merge tool's checkout is a fresh worktree of the repository it runs in, so its packages come from that repository's main checkout. A fresh worktree has none, so a test that imports a package died with "module not found" and read red (q_max #1163: `harness/tests/browser-verify.test.mjs`, `typescript`, green with packages, 34 pass). Picked over reading that exit as unknown: a missing-module exit is also what a real regression looks like, so unknown would open a hole Claude could hit by mistake. A test whose packages neither checkout holds still reads red. Three limits, accepted. The link is the installed folder itself, so a Retire test that writes or deletes inside `node_modules` changes that install (an install repairs it, and Claude does not write such a Retire). The packages are the installed ones, not head's lockfile, so a head that drops a package its test imports can read green here (CI's fresh install catches it). A link the OS refuses (Windows) falls back to red.

Why: a docs-only PR skips review (decision `docs-only-prs-skip-review`, a docs-only PR gets no full review). So a debt can read as closed while its Retire check never ran. Audit 2026-11-06: 35 debt-delete commits since 2026-10-23, 9 of them markdown-only.

Source: lane r2-merge-checks-run-in-ci, restart-plan R2 (owner 14:07 CST Nov 10: the merge tool runs no check that can refuse a green batch; batch #2551 was green in CI and refused at merge by this check's local limit). Coordinator pick a for q_max #1163, 2026-11-12 12:51 CST (link the packages). Coordinator ruling 2026-11-06 13:00 CST (the `Retire-run:` form; a rename out of the folder counts as a close). Coordinator ruling 2026-11-06 13:35 CST (a rename inside the folder with a changed Retire is a close).

Kind: process
Home: lint/check_debt_retire.py
Home: merge/merge.py
Home: lint/check_silent_undo.py
Home: .github/pull_request_template.md
Home: .github/workflows/checks.yml
Check: lint/check_debt_retire.py
