# Browser action prompts come from the app

## The question

The built-in browser pane sometimes asks the owner to approve a click or a typed entry on an
outside website. Can claude-settings turn those prompts off?

## The ruling

Owner, 2026-10-11: no. Record why, so no session tries again.

- `settings.json` already allows every built-in browser tool (`mcp__Claude_Browser`).
- The prompts still come. They come from the desktop app's own safety check on outside
  sites, not from the permission rules in `settings.json`.
- No setting in this repo controls that check. An extra allow rule changes nothing.

## Observed

2026-10-11: with the allow rule in place, an action on an outside site still asked for
approval. Which sites and actions trigger the check is unmeasured. The app does not
publish it.
