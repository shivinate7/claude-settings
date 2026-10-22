Hook import trim and fewer process starts, claude-settings. Roadmap steps: c18 (hooks stop loading code they never use) and c19 lanes 1 to 3 (start fewer processes per tool call). Fixes to existing hooks and mods, not new guard rules. No dispatcher, and no change to how hooks are launched (no exec form, no per-machine settings): those come later. Do not run timing or process-count measurements: the owner has enough numbers. Build the fixes and prove them with tests.

Goal: a hook that has nothing to do for a path or input never loads the guard family, and Claude Code starts fewer bash.exe and python.exe processes per tool call. Every gate keeps exactly its current fail-open or fail-closed behaviour.

Lane 1, prose_judge loads nothing until it has work. In hooks/prose_judge.py, the import `from decision_watch import invoke_model` sits at the top of the file (line 21), so a .ts edit loads the guard family (about 105 modules) before main() checks the path. Move the import into main(), after the is_prose check. Keep the test seam, so a test can still replace invoke_model.

Lane 2, ste_gate loads nothing until it has work. lint/ste_gate.py imports ste_lint (2,290 lines) at the top (lines 53 to 54), only to read UI_SUFFIXES, then checks the suffix in main(). Import ste_lint only after the suffix check. Read UI_SUFFIXES from a small constant that imports nothing, with one home for that list.

Lane 3, the same fix on the other hooks. Check lint/report_gate.py, lint/md_sweep.py, hooks/reply_judge.py, hooks/feedback_gate.py and hooks/ruling_home.py. Any that import guard, decision_watch or ste_lint before they know they have work get the same fix: import after the cheap check.

Lane 4, `if` filters in settings.json, so Claude Code skips the hook without starting a shell. The `if` field takes one permission rule per handler and is checked only on tool events. Docs: https://code.claude.com/docs/en/hooks (Common fields).
- config_watch only: on Write, Edit, MultiEdit and NotebookEdit, run only for the exact file names shared_names lists as watched files.
- Owner's ruling, Oct 21: no filters on ste_gate or prose_judge. A Windows probe showed path patterns with a slash never match (paths arrive with backslashes) and suffix patterns are case-sensitive, so a miss would silently skip the gate. Leave its Bash, PowerShell and Stop runs as they are, since any shell command can write the cap.
Keep each script's own path check as the second layer. Check that a filtered fail-closed handler still blocks when its script is missing.

Lane 5, the decision-watch mod finds Python once. mods/decision-watch/hooks/register.mjs calls pickPython (where.exe, or which) on every Stop. Look Python up once per session and reuse the result. Look again only if the cached path fails to start.

Lane 6, idle polling. Today, each session runs these even when nothing is happening:
- session-board: a git read every 30 s while idle (HEARTBEAT_MS).
- desktop-statusline: 2 git calls every 60 s (REFRESH_MS).
Read git at turn end and on focus or attach. While idle, back off to about 5 minutes. If both mods need the same reading, share one.

Tests, per lane, red on main and green on the fix:
- Lanes 1 to 3: run the hook on an input it ignores (a .ts path for lanes 1 and 2) and assert that no guard-family or ste_lint module is in sys.modules.
- Lane 4: a settings test that an Edit of a watched file matches config_watch and an Edit of any other file does not.
- Lane 5: two Stops in one session start the finder once.
- Lane 6: an idle session runs no git read within the back-off window.

Report:
- Per lane: what changed and the test that proves it.
- The four size numbers on main: decision files, debt files without README and notes.md, hooks/*.py lines (code and tests separately), CLAUDE.md words.
