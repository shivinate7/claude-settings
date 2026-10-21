# decision-watch runs as a mod, on the app's own login

## The ruling

The decision watch runs as a mod on the app's own login, so an expired CLI login no longer silences it. The mod judges each completed main
turn in the background, logs the verdict, and never blocks a turn.

- A FLAG or UNKNOWN verdict shows in the session with `$.ui.toast`. An ALLOW verdict shows nothing (owner ruling).
- Each config notice (config files, merges into main, unread subjects) shows as its own toast, marked as a notice, never a verdict
  (arbiter ruling, 2026-10-14 00:09 CDT). The script prints `verdict` and `notices` as separate JSON fields, so the mod parses no joined
  text.
- `hooks/decision_watch.py` stays the one judge. It has `parse_verdict(text, shape)`, `NeedsModel` (raised when a model call is due), the
  flags `--emit-prompt`, `--model-text` and `--model-error`, a "verdict lost" marker that prints UNKNOWN, and `config_notices(hook)`, which
  `config_report` joins.
- The `claude -p` path stays the default of the script. `invoke_model(prompt, model, timeout, shape)` keeps its signature and return
  shape. `hooks/reply_judge.py` and `hooks/question_outcome.py` call it. A bad flag combination on `decision_watch.py` makes the script use
  `invoke_model`, which can start a 120 s `claude -p` call. The fallback is pinned on purpose.
- Owner, 22:00 CDT ("Fix, then swap"): `enabledPlugins` has `decision-watch@claude-settings`, and no Stop row runs
  `hooks/decision_watch.py`. The mod never enforces.

Reason: a mod's `$.model.complete` ran in the desktop app with no CLI login.

## The event is turn.complete

Owner ruling 2026-10-21 16:28 CDT. The mod listens on `turn.complete`. It does not listen on `classic.Stop`.

- Why: the app's sec-default mod sends every `classic.*` event past the user-tier mods (`on('classic.*', ...)` with `next.to(e, 'append')`).
  So the `classic.Stop` handler never ran. sec-default's README lists `turn.*` as events that pass. This is a read of the marketplace copy of
  sec-default. The installed app's copy is unchecked and may differ.
- A turn with `agentId` set is a subagent turn. The mod skips it, as the session-board mod does.
- `turn.complete` has no transcript path. The mod finds the transcript from the session id and cwd, the way `/dw` does.
- One judge runs at a time. A turn that finds one running logs "SKIP busy".
- The handler returns `next(e)` at once. It never blocks the turn. The `stop_hook_active` skip is gone.
- The move bumps the mod's version.

Protected by `mods/decision-watch/decision-watch.test.mjs`, with one test for each of these:

- a main turn starts a judge;
- a subagent turn (`agentId` set) starts no judge;
- `classic.Stop` starts no judge;
- one judge runs at a time;
- the handler never blocks the turn.

## Unverified

- Live: no "seen" line has been read in `shadow.log` after a real Windows turn. It is pending until the move lands.
- Whether the installed app's sec-default matches the marketplace copy.
- How long `$` lives after the handler returns, for a background judge that nothing awaits.

Kind: process
Home: mods/decision-watch/hooks/register.mjs
