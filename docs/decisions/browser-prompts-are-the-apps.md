# Browser action prompts come from the app

## The ruling

Owner, 2026-10-11: claude-settings cannot disable the built-in browser pane's approval prompts on outside sites. No session tries again.

- `settings.json` already allows every built-in browser tool (`mcp__Claude_Browser`).
- The prompts come from the desktop app's own safety check, not from `settings.json`. An extra allow rule changes nothing.
- Measured 2026-11-21: the app asks before it opens a file outside the session's folder that sits in a folder on its sensitive list (`.claude`, `.git`, `.ssh`, `.aws` and others, read from the app bundle, Claude desktop 6.28899.6). The card offers only Deny and Allow once. It ignores bypass mode and never times out. Agent worktrees sit under `.claude/worktrees`, so an agent that opens its own file there hits it. Which outside sites trigger it stays unmeasured.

## Guard

Owner, 2026-11-21 13:58 CST, "ya approved": refuse the call, and point at the solution, headless Chrome.

- Rule `agent-browser-file-open` in `hooks/guard.py` refuses a call by an agent (a non-empty `agent_id`) that opens a `file:` URL. The scheme is read in any case. The calls are `mcp__Claude_Browser__navigate` and `mcp__Claude_Browser__preview_start` (`url`), and each `navigate` or `preview_start` item of `mcp__Claude_Browser__browser_batch` (its input `url`).
- The reason says a file opened in the built-in browser can stop on an app card nobody answers. It names headless Chrome (Playwright) or a localhost URL as the way.
- The main session passes: a person sees its card. A localhost or https URL passes. An owner override lifts the rule.
- Incident: 2026-11-21, a designer agent in the home repo opened its mockup by `file://` and waited 12 hours (01:13 to 13:13 CST).
- Cost: one guard run per `navigate`, `preview_start` or `browser_batch` call, from the three tools added to the guard's PreToolUse matcher in `settings.json`.

Kind: process
Home: hooks/guard.py and settings.json
