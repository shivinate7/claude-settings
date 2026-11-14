# start_session is not gated at PreToolUse

## The ruling

Owner, typed in the triage chat 00:12 CST Nov 14, 2026 (ruling `own-809-reopen-hook-card`, item 809 reopened): "Reopen 809." No PreToolUse matcher in `settings.json` lists `mcp__ccd_session__start_session`, and none is a regex or `*` that covers it. The start checks run some other way that adds no PreToolUse hook on that tool. This decision picks option (b): a PostToolUse audit.

- **The cause.** The desktop app (Claude.app 5.11492.5) counts any non-built-in PreToolUse hook whose matcher covers `start_session` as an ask rule, even when the hook answers allow. It then shows the "Allow Claude to start the session?" card on every start, even in Bypass. A remote flag (3650263018) marks `start_session` "always_ask", which makes the check run. App path, as the owner read it: `createCanUseTool` -> `_e` -> `t.i$` (`aDr`) -> `iDr`, which returns true for any non-built-in PreToolUse hook whose matcher covers the tool. The lane that wrote this record did not read that path: `app.asar` is not in the cloud. Public bug: anthropics/claude-code#103832 (open). `permissions.allow` and allow hooks do not help; they make it worse.
- **The proof.** Owner test, 00:04 CST Nov 14: with `start_session` removed from every PreToolUse matcher, a fresh Bypass session started a session with no card. With it restored, the card came back.
- **The audit.** `settings.json` has one PostToolUse entry for `mcp__ccd_session__start_session`. It runs `hooks/start_session_audit.py`. The audit flags a start whose `model` is below the floor (`guard.floor_hit`, the one reading) and a start made while the calling session's handoff is unread (`reread_check.unread_handoff`, the guard's own read). A flagged start prints PostToolUse `additionalContext` that names the new session (`session_<id>`, read from the start result, or "id is unread") and tells the calling session to stop it with `interrupt_session` or `archive_session`. A good start prints nothing, and so does a start result that shows no session started (an `is_error`, `isError` or `deny` flag, or a result that is not text, a list or a dict). A bad payload or a failed read prints nothing: the audit fails open.
- **The test.** `lint/test_settings_matcher.py` (class `StartSessionNotPreToolUse`) fails when any PreToolUse entry covers `start_session`, in any matcher form (absent, empty, `*`, a pipe list, a regex). Its cases in `tests/guard/` (family `start-session-audit`) pin the audit.

## Why (b)

(a), the next gated call, catches only an unread handoff, and only on a tool the matcher lists; it never sees a model below the floor. (c), dropping the checks, would let a Haiku session start and run unflagged, and the triage brief reports real denies on these checks in `guard.log` (handoff-unread and agent-model-floor; unmeasured here, the cloud has no `guard.log`). (b) keeps both of those checks, at the cost of acting after the start, not before it.

## Checks lost at PreToolUse

Read in `hooks/guard.py`: `judge` refuses before the call. `start_session` was named by `floor_hit` (rule `agent-model-floor`) and by `load_hit` through `START_TOOLS` (rule `load-brake`); no other rule names `SESSION_TOOL`. Every other rule that applied did so because the tool was in the matcher, and the only one that reads a call of any tool is `handoff-unread`.

- **Model floor.** Was a deny before the start. Now flag-only: a Haiku session starts, and runs until the calling session reads the flag and stops it. Harm: one Haiku session's work and spend, if the caller does not act on the flag. Debt `start-session-checks-after`. The guard's judge still denies a Haiku start if a matcher is added again.
- **Handoff-unread on the start call.** Was a deny of the start call itself. Now flag-only after the call. Harm: a new session started on a brief written without the handoff, until the caller stops it. The caller's next call on any listed tool is still refused until it reads the handoff (the guard's check 0 on that call), so the gap is the start itself. Debt `start-session-checks-after`.
- **Full-machine load brake.** Was a deny of a start at full (memory over 95%, or disk free under the smaller of 5% and 5 GB). `start_session` was never refused at busy. Now lost, with no replacement: the audit reads no load, because stopping a session after it started frees nothing at the moment the machine is full. Harm: a lane started on a full machine, the 2026-10-26 incident shape (decision `machine-load-brake`). Agent, Task and Workflow stay braked. Debt `start-session-load-unbraked`.
- **Other `START_TOOLS` rules.** None. `START_TOOLS` feeds only `load_hit`.

## What stays in code

`SESSION_TOOL`, `START_TOOLS` and the `start_session` branch of `floor_hit` stay in `hooks/guard.py`. The audit calls `floor_hit`, and the guard's cases call `judge` on a `start_session` payload. No PreToolUse call reaches them.

Why: a hook on a tool the owner must answer a card for makes every start an interruption. The audit gives the same two checks with no card.

Cost, per `outcomes-mechanize-rules`: process starts, one per `start_session` call, none on any other call. Files written, none. It reads the handoff flag file (one existence check, and the handoff file only when the flag exists) and imports the guard module once per start. No timer and no watcher. `lint/test_settings_matcher.py` and the `start-session-audit` family pin the wiring and the verdicts.

Kind: build
Plan: docs/decisions/start-session-not-pretooluse.md#the-ruling (macos)
Plan: docs/decisions/start-session-not-pretooluse.md#the-ruling (windows)
Plan: docs/decisions/start-session-not-pretooluse.md#the-ruling (linux)
