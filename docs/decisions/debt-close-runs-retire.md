# A debt close runs its Retire check

## The ruling

A PR closes a debt when it deletes the debt file, or renames it out of `docs/debts/`. A rename inside that folder is not a close, unless its Retire paragraph changed: then it is a close, and the Retire text at base runs.

- The shared merge tool reads the debt's Retire text at base. For each runnable check that text names:
  - No CI step runs it: the tool runs it on the PR head, in preview and in confirm.
  - A CI step runs it: the tool reads that step's result, as set out below.
- A red check refuses the close. A check that cannot run refuses it too (decision `ci-unknown-is-red`, an unknown read is red).
- A PR with no runnable check is refused. The way out, for no runnable check or one that cannot run (an unknown CI read counts): the PR body holds `Retire-run: <slug> -- <run URL>`, for a run that succeeded on the PR head or on a descendant of it. A cite never clears a red check.
- A runnable check is a backticked path in the Retire text. The path is tracked at head and named like a test file: `test_*.py`, `*_test.py`, `*.test.mjs`, `test_*.mjs` or `test_*.sh`. Its extension sets the runner: `python3`, `node --test` or `bash`. No shell, no model call.
- An isolated run (the merge tool, the CLI) links installed `node_modules` into the scratch worktree, at the root and beside each tracked `package.json`. Each folder comes from the checkout the check reads when it has one, else from the main checkout of that repository. The merge tool's checkout is a fresh worktree of the repository it runs in, so its packages come from that repository's main checkout. A fresh worktree has none, so a test that imports a package died with "module not found" and read red (q_max #1163: `harness/tests/browser-verify.test.mjs`, `typescript`, green with packages, 34 pass). Picked over reading that exit as unknown: a missing-module exit is also what a real regression looks like, so unknown would open a hole Claude could hit by mistake. A test whose packages neither checkout holds still reads red. Three limits, accepted. The link is the installed folder itself, so a Retire test that writes or deletes inside `node_modules` changes that install (an install repairs it, and Claude does not write such a Retire). The packages are the installed ones, not head's lockfile, so a head that drops a package its test imports can read green here (CI's fresh install catches it). A link the OS refuses (Windows) falls back to red.
- A check that a CI step runs is judged from CI. It runs once, in CI, and never here, unless its step was skipped.
  - The CI steps are those of `.github/workflows/checks.yml` at the PR head whose `run:` names the check's path as a whole word.
  - The tool reads the newest `pull_request` run named `checks` on the PR head that did not end skipped. It reads each named step's result from that run. A matrix job matches as `name (value)`.
  - Draft PR: the close is deferred. The tool prints `merge: debt <slug>: deferred to confirm: no run exists yet`. A deferred close neither passes nor refuses, and excuses no silent-undo delete. Any other check in the same Retire still runs here, and a red one refuses.
  - Ready PR: the check passes only when each named step is `success` on a run whose sha is the PR head or a commit above it. Red outranks unknown, and unknown outranks skipped.
    - Red: a step that ends `failure` or `timed_out`.
    - Unknown, which refuses:
      - no run, or no such step in it;
      - a step not finished;
      - a run on another commit, or on a commit this checkout does not hold;
      - a run that could not be read;
      - any other end, such as `cancelled`.
    - Skipped (the scope is off, so the step never ran): the check runs here, as before. That local run is the evidence main had.
- A check no CI step names runs here, as before. A debt with no Retire line is judged as before. The `Retire-run:` cite stays. The CLI (`lint/check_debt_retire.py`) reads no CI run, so it runs every check here.

Why: a docs-only PR skips review (decision `docs-only-prs-skip-review`, a docs-only PR gets no full review). So a debt can read as closed while its Retire check never ran. Audit 2026-11-06: 35 debt-delete commits since 2026-10-23, 9 of them markdown-only.

Why CI reads the close: `merge --ready`, `--fast-checks` and both confirm calls ran `hooks/test_guard.py` here, about 39 min (one measurement), and the PR's CI then ran it again. Rule `roles-each-layer-proves-once` (each layer proves a change once) says the PR run is the merge check.

Departs from: main ran a check that a CI step names, locally, at ready, fast-checks and confirm. This runs it once, in CI, and the merge reads the result.

Known limits, unmeasured:
- A step that names the check in a non-test command, such as `git add`, counts as naming it.
- The CI run's tree is the PR head, not a fresh merge with the base. The base check (`holds_base`, merge/merge.py) covers a base that moved on: it passes a head only when it merges cleanly with the base tip.

Source: coordinator pick, 2026-11-14 20:32 CST, under the owner's goal of 2026-11-14 20:17 CST ("max efficiency with no waste and remaining accurate"), for roadmap step `debt-close-reads-ci` (CI reads the close). Coordinator pick a for q_max #1163, 2026-11-12 12:51 CST (link the packages). Coordinator ruling 2026-11-06 13:00 CST (the `Retire-run:` form; a rename out of the folder counts as a close). Coordinator ruling 2026-11-06 13:35 CST (a rename inside the folder with a changed Retire is a close).

Kind: process
Home: lint/check_debt_retire.py
Home: merge/merge.py
Home: lint/check_silent_undo.py
Home: .github/pull_request_template.md
Check: lint/check_debt_retire.py
