# decision-watch runs as a mod, on the app's own login

## The ruling

The Stop-time decision watch runs as a mod on the app's own login, so an expired CLI login no longer silences it. The mod judges each Stop in the background, logs the verdict, and never blocks a turn.

- A FLAG or UNKNOWN verdict shows in the session with `$.ui.toast`. An ALLOW verdict shows nothing (owner ruling).
- Each config notice (config files, merges into main, unread subjects) shows as its own toast, marked as a notice, never a verdict (arbiter ruling, 2026-10-14 00:09 CDT). The script prints `verdict` and `notices` as separate JSON fields, so the mod parses no joined text.
- `hooks/decision_watch.py` stays the one judge. It has `parse_verdict(text, shape)`, `NeedsModel` (raised when a model call is due), the flags `--emit-prompt`, `--model-text` and `--model-error`, a "verdict lost" marker that prints UNKNOWN, and `config_notices(hook)`, which `config_report` joins.
- The `claude -p` path stays the default of the script. `invoke_model(prompt, model, timeout, shape)` keeps its signature and return shape. `hooks/reply_judge.py` and `hooks/question_outcome.py` call it.
- Owner, 22:00 CDT ("Fix, then swap"): `enabledPlugins` has `decision-watch@claude-settings`, and no Stop row runs `hooks/decision_watch.py`. The mod never enforces.

Why: a mod's `$.model.complete` ran in the desktop app with no CLI login. A full judgment took about 5 s.

Protected by `mods/decision-watch/decision-watch.test.mjs`.

## Holes, named

Unverified:

- Whether `classic.Stop` reaches a mod in the desktop app.
- How long `$` lives after `classic.Stop` returns, when the background call is `void shadow`.
- Whether the host stops a model call at `timeoutMs`. The mod enforces 50 s itself with a timer race that frees the slot.
- Whether `$.process.run` kills the child at `timeoutMs`. The mod's timer frees the slot but does not kill the child.
- The exit code of `where.exe python3 python` when only `python` exists.

Limits:

- A bad flag combination on `decision_watch.py` makes the script use `invoke_model`, which can start a 120 s `claude -p` call. The fallback is pinned on purpose.
- Not built: `guard_core._force_utf8_streams` should also reconfigure stdin, else the script reads raw non-ASCII stdin wrongly on Windows. No lane owns it.

Kind: process
Home: mods/decision-watch/hooks/register.mjs
