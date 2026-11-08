# In CI, an unknown read is red

## The ruling

One rule for every check (owner, 2026-11-06 12:39 CST, waiting-page item 276, pick a). A check that cannot read its input prints UNKNOWN. Locally it exits 0. When env `CI` is set it exits non-zero, because the CI exit code is the verdict (`verification-report-unknown-reads`, report a read that could not run as unknown). A check that needs history or a ref it lacks fetches it first. It is UNKNOWN only when the fetch fails too, so a child repo on a shallow checkout is not red for a non-defect.

Why: a green exit on an unread input hides a defect.

Homes with this shape:

- `lint/check_record_slugs.py`, `lint/check_silent_undo.py`, `lint/check_ruling_kind.py`.
- `lint/check_glossary.py`, `lint/check_artifact_cites.py` (an absent records folder is zero records, which is an answer), `lint/ste_lint.py` (an unparseable config).
- `lint/stale_cites.py`, for a file it cannot read.

One exception holds today: `lint/stale_cites.py` does not fetch a base that a shallow clone lacks. It prints `stale-cites: unknown, ...` and exits 0, CI or not (`stale-cites-at-merge`, owner-lane call, 2026-11-01). Whether item 276 a ends that exception is open with the coordinator.
- `actions/code-check/code_check.py` and `actions/ci-alarm` (`alarm.sh`, `dropped.sh`, `issue.sh`).

Stricter, red locally too: `lint/check_comment_narration.py` (exit 2), `hooks/mutate_guard.py --known-defects`, and the other lints, which exit 1 or 2 on a failed read. `ci-scope.sh` fails safe by running the harness. `actions/stamp` keys on `GITHUB_ACTIONS`, not `CI`.

Out of scope, with the reason:

- `actions/mutation-report` step 1 and `actions/ci-done-comment`: a report and a notifier, not checks.
- `lint/check_claude_md_size.py`: warn-only. An unread file hides a warning, never a red.
- `lint/layout.py` `has_extras()`: a missing `.claude/layout-extras.json` means "none declared". That is an answer, not an unread input.
- `lint/compliance_probes.py` and `lint/find_copies.py`: no CI runs them.
- A check the tool does not build is a limit, not an unread input. It prints a note and exits 0. Today: `skills/plain-english-map/scripts/map-check.mjs` `modelSeam` (the command binds no reader), and `lint/stale_cites.py` cites of JavaScript and shell names (`stale-cites-at-merge`).

A caller's opt-out covers findings only. ste-lint with `fail: false` (`--fail-on never`) is still red in CI on an unread input (owner item 276 a, applied by the coordinator 2026-11-06 13:31 CST).

Where CI runs a suite is in `test-strategy-reset` (tests prove outcomes, run where their subject lives).

Kind: process
Home: lint/check_record_slugs.py
Home: lint/check_silent_undo.py
Home: lint/check_glossary.py
Home: lint/check_artifact_cites.py
Home: lint/ste_lint.py
Home: lint/stale_cites.py
Home: actions/code-check/code_check.py
Home: actions/ci-alarm/alarm.sh
