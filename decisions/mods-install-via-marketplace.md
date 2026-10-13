# Mods install from the claude-settings GitHub marketplace, with no installer step

## The question

How does a mod from this repo reach every PC and Mac of the owner, with no step that a person must run?

## The ruling

The shared `settings.json` declares one marketplace, `claude-settings`. Its source is the GitHub repo `shivinate7/claude-settings`. The same file enables four mods by key: `token-weather`, `desktop-statusline`, `plain-diff`, and `session-board`. The file `.claude-plugin/marketplace.json` lists all four.

Owner intent: work saved in this repo must carry across repos and devices, the Mac included. No machine path goes in a shared file.

Why not a local-path marketplace: `marketplace add <clone path>` writes an absolute path into `settings.json`. On a Mac, that file is a link to the shared copy. One machine path would then reach every machine.

Owner word, 2026-10-13 12:22 CDT, relayed by the merge session: enable the marketplace entry and all four keys.

## What was tested

On 2026-10-13 the owner tested `plain-diff` and `session-board` in the Windows desktop app. Both draw. The `/board` pane shows the permission-wait state. Nobody has yet shown `token-weather` or `desktop-statusline` in the desktop app.

## Holes, named

- macOS is untested for all four mods.
- The marketplace source has no `ref` pin. It follows the default branch. A bad merge to main reaches every machine at its next plugin refresh. Review and CI on main are the only guard.
- A mod loads only in a session that starts after the change. A running session keeps its old mod set.
- Unmeasured: how often the app refreshes a marketplace, and whether it refreshes while a session is open.

Kind: process
Home: settings.json
