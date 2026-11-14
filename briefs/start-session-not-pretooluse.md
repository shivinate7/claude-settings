# Brief: start_session is not gated at PreToolUse (step start-session-not-pretooluse)

Lane brief. Owner's words, typed in the triage chat 00:12 CST Nov 14 (ruling own-809-reopen-hook-card), reopening item 809. Triage did not check the app code path; it is the owner's test.

## Task

The Claude desktop app shows an "Allow Claude to start the session?" card on every `mcp__ccd_session__start_session` call, even in Bypass mode, because our guard hook lists that tool.

Proven cause (owner test, 2026-11-14 00:04 CST):
- The desktop app (Claude.app 5.11492.5) counts any PreToolUse hook whose matcher lists `mcp__ccd_session__start_session` as an "ask" rule, even when the hook answers "allow". In app.asar `.vite/build`: createCanUseTool -> _e -> t.i$ (aDr) -> iDr returns true for any non-built-in PreToolUse hook whose matcher covers the tool. A regex-like matcher such as `*` counts too. A remote flag (3650263018) marks start_session "always_ask", which makes this check run.
- `settings.json`, hooks.PreToolUse entry 0 (the guard.py hook), lists `mcp__ccd_session__start_session` in its matcher. That alone causes the card on every start.
- Test: with start_session removed from every PreToolUse matcher, a fresh Bypass session started a session with no card. With it restored, the card came back.
- Public bug: anthropics/claude-code#103832 (open). `permissions.allow` and allow hooks do not help; they make it worse.

What the guard checks on start_session today (`hooks/guard.py`; line numbers are the owner's, unchecked): SESSION_TOOL at ~2913. The model floor in floor_hit (~3072). The START_TOOLS checks (~4074): handoff-unread and related start rules. A load-brake skip (~4170). guard.log shows real denies on it: handoff-unread and agent-model-floor.

1. Remove `mcp__ccd_session__start_session` from the PreToolUse matcher in `settings.json`. A broader regex matcher would also trigger the card, so use none.
2. Keep the start checks some other way that adds no PreToolUse hook on this tool. Pick and justify one: (a) the same checks fire on the session's next gated tool call (handoff-unread already does on Bash/Edit); (b) a PostToolUse audit on start_session that flags a bad start (wrong model, unread handoff) and tells the session to stop the new session; (c) drop the checks for start_session, with a debt record. Say which checks are lost, and the harm.
3. Tests: a test that settings.json's PreToolUse matchers never list `mcp__ccd_session__start_session` or a regex covering it, with a comment naming the app behaviour and issue #103832. Show it red first on the current `settings.json`. Update the guard tests that expect start_session to be judged at PreToolUse.
4. Record: a decision record for "start_session is not gated at PreToolUse", citing the owner test and the app code path. Update any rule or doc that says the guard gates start_session.

## Triage notes for the lane

- Touches a guard's verdict and `settings.json`: a lane builds it; review rounds apply (rule roles-review-cap-three). A test-author writes the red test first (rule roles-each-layer-proves-once).
- Related rows: step c107 and item 751 (the same hook family; separate question, stays open); step local-autonomy-equals-cloud (lane session_013NEJL2xbx9cwQLXuRSA66d held item 809).
- Check, for failure classes (outcomes-tests-are-statements): any test that expects a start_session deny at PreToolUse is stale by this ruling; re-point it red then green. Any scanner over `settings.json` matchers must read every matcher form (list, pipe-joined string, `*`, regex).
- Done check: the new settings test is green; it was red on the old `settings.json`; the guard tests pass; the decision record is on main; one fresh Bypass session started a session with no card (the owner runs that last test; no cloud session can).
- Report cap: 25 lines. Say which of a, b or c you chose, which checks are lost, and the harm.
