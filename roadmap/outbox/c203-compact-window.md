# c203 compact-window-off-tracked-file (lane session_013NEJL4Ghu7Kthvr3kBsiVR)

Lane ships defect 2 only: the handoff hook reads the window in use. The per-tier route waits for shiv's pick on waiting-page item 61 (on hold since 19:43 CDT, 2026-10-28).

Measured 2026-10-28, Claude Code 2.1.312:
- `/autocompact 300k` writes user settings, as `modelSettings.<model>.autoCompactWindow`, through the symlink into the pinned checkout, so that repo shows ` M settings.json`.
- With `CLAUDE_CODE_AUTO_COMPACT_WINDOW` set, `/autocompact` refuses ("is set and takes precedence") and writes nothing.
- Claude Code reads one user-scope settings file only.

Measurements for item 61:
1. The variable raises the window too: `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000` gave effective window 980000, source env, live. 400000 gave 380000.
2. An agent's window = the smaller of the session window (variable included) and the agent's own `autoCompactWindow`. A builder at 300000 gets 300000 under 400000 and 200000 under 200000. Read from the binary's resolver; a live agent probe emitted no window state, so the live read is unknown.
3. Only builder was named for a row. test-author, reviewer and record-writer also run long in lanes and may want one.
