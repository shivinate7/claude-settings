# The hook `if` field filters only the config watch

## The ruling

Owner, 2026-10-21. The `if` field of a Claude Code hook filters only `config_watch`, by exact file names. The `prose_judge` suffix filter is parked. The `ste_gate` hook is removed (`ste-guard-fixes-not-nags`). A guard that silently skips is not worth the saving (`guard-hooks-fail-closed`, a guard whose script is missing refuses the call).

Reopen the suffix filters only when both are true:

- The Windows process-churn fixes have landed.
- The memory monitor runs again, and the shell starts on Edit and Write still look significant.

The lane that applies this ruling is [PR #551](https://github.com/shivinate7/claude-settings/pull/551), a draft.

## Probe facts

Probe run 2026-10-21. Claude Code 2.1.296, Windows 11, NTFS.

- Slash patterns, such as `**/decisions/**` and `**/*.md`, never match on Windows, because tool paths arrive with backslashes. Do not use slash patterns.
- A suffix pattern, such as `*.md`, matches by suffix. It matches in any folder, and outside the cwd.
- A suffix pattern is per tool. An `Edit(...)` rule does not fire for Write.
- A suffix pattern is case-sensitive. `*.md` misses `README.MD`.
- A missing hook script exits 127. Exit 127 does not refuse.

Kind: process
Home: settings.json
