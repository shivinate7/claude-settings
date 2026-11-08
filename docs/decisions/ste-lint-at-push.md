# The STE lint runs once at push

## The ruling

Rule `ste-push` in `hooks/guard.py` refuses a `git push` when the CI STE lint would fail on the Markdown it sends. Its home is `ste_push_hit` in `hooks/guard_merge.py`, with the lint runner in `hooks/guard_ste.py`. Owner, 2026-11-07 19:03 CST, page item 377, option a: allow the push-time lint.

- The mistake: a lane pushed four notes with sentences over 30 words. Only a later lint caught them (lane replay-profile-parts, PR 1653, 2026-11-07 17:44 CST).
- The harm: CI fails after the push. The review record then sits on a head that moves, and the fix costs one more fix check.
- It does not run on a write. Decision `ste-guard-fixes-not-nags` (no STE hook on a write) still holds for Write, Edit and MultiEdit. A push is not a write: one check per push, never per edit.
- Scope: the `paths`, `changed_paths` and `exclude` defaults in `actions/ste-lint/action.yml`, plus `.ste-lint-exclude`. `hooks/guard_ste.py` is the one reader; `bin/ste-changed` imports it.
- The range: from origin's default branch to the pushed ref, as CI's base is, never the push's own destination. A lane that merged main is judged on its own changes. `conflict-markers` keeps the destination range (`commit-refuses-conflict-markers`).
- The pinned CI step's `with:` block, read from the pushed checkout's workflow: `fail: false` allows with no lint; `exclude` is applied to the scope and the lint; any other input not at its default reads unknown. A default reads the same quoted or unquoted, so `scope: changed` is no input.
- `lint/workflow_steps.py` reads each CI step list at its own indent, so 6-space and 4-space layouts both read. A line that pins the action with no CI step the reader parses (a flow mapping, say) reads unknown.
- A commit earlier in the same call is not in the push's range. With an in-scope file staged or dirty, the push is denied: push in a call of its own. No lint starts. A `git commit` with no `-a` that leaves an in-scope edit unstaged is refused too; that costs one retry.
- A merge, cherry-pick, am or revert earlier in the call makes a commit the push cannot lint either. It is denied the same way when it brings an in-scope file. A merge of origin's default branch brings nothing, so it is allowed. An am patch is not read, so an am before a push is denied; a code-only patch costs one retry.
- Only the `ste-lint:` verdict line decides. FAIL refuses. PASS allows. A stale-cites failure alone does not refuse; CI still catches it.
- Unknown allows, with a noted guard.log line and "unknown" in the output. Unknown is a crash, a timeout (40 s), an exit other than 0, 1 or 3, no verdict line, "no markdown changed", or a pushed ref other than HEAD. Why: CI still carries the lint, and a check that blocks on its own fault cries wolf (`guard-that-cries-wolf-is-spent`).
- Pin drift never refuses, even with a FAIL line: the pinned CI may lint with older files and pass. Drift is exit 3, or a FAIL with the drift line that `bin/ste-changed` prints on stdout (its text is `PIN_DRIFT` in `hooks/guard_ste.py`). `bin/ste-changed` exits 2 on its own faults, never 1.
- Limits: a push in a subshell whose `)` touches its last word, as in `(git push origin topic)`, reads unknown. A `bash -c` script is not read. A pull earlier in the call is not read.
- Skipped, no lint: `--delete`, a tags-only push, `-n` or `--dry-run`, and a destination under `archive/`. CI runs no lint on these. The record branch is skipped too: it holds records that never merge to main, so CI's PR lint never reads them. Also skipped: a repo whose CI does not run the ste-lint CI step (no `claude-settings/actions/ste-lint@` pin, and not claude-settings itself).
- Cost: a merge, cherry-pick or revert before the push adds one `git diff` read per ref it names, two for a merge. A push with no file in scope starts no lint process. A push with files in scope starts one `ste-changed` run. That run starts one bash, up to four Python processes and some git reads. It runs a `git fetch` only when the remote-tracking base is missing. Measured: 1.16 to 1.32 s for a one-file push (n 3), 7.6 s for 138 files (n 1). No log, file or long-lived process. `hooks/test_guard_ste_push.py` proves the zero-start case.

Protected by `hooks/test_guard_ste_push.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
