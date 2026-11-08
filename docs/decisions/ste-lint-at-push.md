# The STE lint runs once at push

## The ruling

Rule `ste-push` in `hooks/guard.py` refuses a `git push` when the CI STE lint would fail on the Markdown it sends. Its home is `ste_push_hit` in `hooks/guard_merge.py`, with the lint runner in `hooks/guard_ste.py`. Owner, 2026-11-07 19:03 CST, page item 377, option a: allow the push-time lint.

- The mistake: a lane pushed four notes with sentences over 30 words. Only a later lint caught them (lane replay-profile-parts, PR 1653, 2026-11-07 17:44 CST).
- The harm: CI fails after the push. The review record then sits on a head that moves, and the fix costs one more fix check.
- It does not run on a write. Decision `ste-guard-fixes-not-nags` (no STE hook on a write) still holds for Write, Edit and MultiEdit. A push is not a write: one check per push, never per edit.
- Scope: the `paths`, `changed_paths` and `exclude` defaults in `actions/ste-lint/action.yml`, plus `.ste-lint-exclude`. `hooks/guard_ste.py` is the one reader; `bin/ste-changed` imports it.
- The range: from origin's default branch to the pushed ref, as CI's base is, never the push's own destination. A lane that merged main is judged on its own changes. `conflict-markers` keeps the destination range (`commit-refuses-conflict-markers`).
- The pinned step's `with:` block, read from the pushed checkout's workflow: `fail: false` allows with no lint; `exclude` is applied to the scope and the lint; any other input not at its default reads unknown.
- A commit earlier in the same call is not in the push's range. With an in-scope file staged or dirty, the push is denied: push in a call of its own. No lint starts.
- Only the `ste-lint:` verdict line decides. FAIL refuses. PASS allows. A stale-cites failure alone does not refuse; CI still catches it.
- Unknown allows, with a noted guard.log line and "unknown" in the output. Unknown is a crash, a timeout (40 s), an exit other than 0, 1 or 3, no verdict line, "no markdown changed", or a pushed ref other than HEAD. Why: CI still carries the lint, and a check that blocks on its own fault cries wolf (`guard-that-cries-wolf-is-spent`).
- Exit 3 (pin drift) never refuses, even with a FAIL line; that reads unknown. `bin/ste-changed` exits 2 on its own faults, never 1.
- Skipped, no lint: `--delete`, a tags-only push, `-n` or `--dry-run`, a destination under `archive/`, the record branch. Also skipped: a repo whose CI does not run the ste-lint step (no `claude-settings/actions/ste-lint@` pin, and not claude-settings itself).
- Cost: a push with no file in scope starts no lint process. A push with files in scope starts one `ste-changed` run: bash, one Python lint, git reads, and a `git fetch` only when the remote-tracking base is missing. Measured: 1.16 to 1.32 s for a one-file push (n 3), 7.6 s for 138 files (n 1). No log, file or long-lived process. `hooks/test_guard_ste_push.py` proves the zero-start case.

Protected by `hooks/test_guard_ste_push.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
