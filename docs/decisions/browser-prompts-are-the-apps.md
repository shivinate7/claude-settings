# Browser action prompts come from the app

## The ruling

Owner, 2026-10-11: claude-settings cannot disable the built-in browser pane's approval prompts on outside sites. No session tries again.

- `settings.json` already allows every built-in browser tool (`mcp__Claude_Browser`).
- The prompts come from the desktop app's own safety check, not from `settings.json`. An extra allow rule changes nothing.
- Unmeasured: which sites and actions trigger the check. The app does not publish it.

Kind: process
Home: settings.json
