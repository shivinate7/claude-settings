# Decision watch finds the transcript by session id when the given path fails

## The ruling

When the transcript path given to the decision watch is missing or does not exist, the decision
watch finds the transcript by session id. The script `hooks/decision_watch.py` judges the path it is
given. The silent no-transcript case belongs to the mod `mods/decision-watch`
(`mods/decision-watch/hooks/register.mjs:82`).

- The UNKNOWN for a failed path names the path it tried. It shows once per session for the
  background judge.
- The mod's silent no-transcript case (`mods/decision-watch/hooks/register.mjs:82`) shows once per
  session too.

Owner, 2026-11-11 13:36 CST: "r41 yes on all". That covers all seven R41 items. This record files
item 1 only (restart plan R41).

Coordinator pick, 2026-11-12 09:30 CST. This is not an owner ruling. The once-per-session
UNKNOWN above, from the owner ruling of 2026-11-11 13:36 CST, applies to the background judge
only. An explicit `/dw` that the owner asks for shows the UNKNOWN on every miss. The rule
`verification-report-unknown-reads` (an unread is never reported as clear) governs that read.

Red cases first. Each case below gets a test:

- a path with Windows backslashes;
- a path with a drive letter;
- a path that starts with `~`;
- a Git Bash path, such as `/c/...`;
- a second config dir;
- a long folder name.

This narrows one sentence in the Stop guardrail record, decision `stop-guardrail-became-a-command-hook`.
That sentence says the cap never applies to an UNKNOWN read. For this one UNKNOWN, the failed-path
UNKNOWN, the cap applies: it shows once per session for the background judge. Other UNKNOWN
reads keep the older rule. The older sentence stays true of the code until this build lands.

## Not built

The fallback is not built. What exists now:

- The mod builds the transcript path from the session id and cwd on each turn, in `deriveStop` in
  `mods/decision-watch/hooks/register.mjs`.
- `hooks/decision_watch.py` uses only the path it is given. When that path is missing or does not
  exist, it reports UNKNOWN and stops. That UNKNOWN names no path and is never cached.
- When the mod finds no transcript, it logs `SKIP no transcript` and shows nothing.

Cost, once built: runs only when the given path fails. One path build per config dir. Once per
session, one mark in the script's seen store.

Kind: build
Plan: docs/plans/restart-plan.md#315-spend-fewer-tokens-measured-first (all)
