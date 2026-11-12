# Decision watch finds the transcript by session id when the given path fails

## The ruling

When the transcript path that `hooks/decision_watch.py` is given is missing or is not a file, the
script finds the transcript by session id and cwd. It builds the path the way the mod does, in
`deriveStop` in `mods/decision-watch/hooks/register.mjs`.

- The UNKNOWN for a failed path names the path it tried. It shows once per session.
- The silent no-transcript case shows once per session too.

Owner, 2026-11-11 13:36 CST, restart plan R41 item 1: "r41 yes on all".

Red cases first. Write a test for each case below, and see it go red on the current script before
the fallback is built:

- a path with Windows backslashes;
- a path with a drive letter;
- a path that starts with `~`;
- a Git Bash path, such as `/c/...`;
- a second config dir;
- a long folder name.

## Not built

The fallback is not built. What exists now:

- The mod builds the transcript path from the session id and cwd on each turn.
- `hooks/decision_watch.py` uses only the path it is given. When that path is missing or not a file,
  it reports UNKNOWN and stops. That UNKNOWN names no path and is never cached.
- When the mod finds no transcript, it logs `SKIP no transcript` and shows nothing.

Cost, once built: runs only when the given path fails. One path build and one file check. Once per
session, one mark in the script's seen store.

Kind: build
Plan: docs/plans/restart-plan.md#315-spend-fewer-tokens-measured-first (all)
