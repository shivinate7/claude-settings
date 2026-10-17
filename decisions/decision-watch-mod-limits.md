# decision-watch runs as a mod, on the app's own login

## The question

Can the Stop-time decision watch run as a mod, with the app's own login and no CLI login? If it can, a login that expires no longer silences the watch.

## The ruling

Yes. The mod judges each Stop in the background, logs the verdict, and never blocks a turn. A FLAG or UNKNOWN verdict shows in the session with `$.ui.toast`. An ALLOW verdict shows nothing (owner ruling: ALLOW stays silent). That ruling covers verdicts only, and each config notice (config files, merges into main, unread subjects) shows as its own toast, marked as a notice, never a verdict (arbiter ruling, 2026-10-14 00:09 CDT). Under the split flags, the script prints `verdict` and `notices` as separate JSON fields, so the mod parses no joined text.

`hooks/decision_watch.py` stays the one judge. It gains:

- `parse_verdict(text, shape)`. It reads a model reply and returns a verdict.
- `NeedsModel`. The cheap path raises it when a model call is due.
- The flags `--emit-prompt`, `--model-text` and `--model-error`.
- A "verdict lost" marker. It prints UNKNOWN.
- `config_notices(hook)`, the notice list. `config_report` joins it.

The old `claude -p` path stays the default of the script. `invoke_model(prompt, model, timeout, shape)` keeps its signature and its return shape. `hooks/reply_judge.py` and `hooks/question_outcome.py` call it.

Enabling: the owner ruled 22:00 CDT ("Fix, then swap"). HOLE 1 is closed. `enabledPlugins` has `decision-watch@claude-settings`, and the Stop row that ran `hooks/decision_watch.py` is removed. The mod still never enforces.

## Why

On 2026-10-13 at 12:09 CDT, a spike ran a mod's `$.model.complete` in the desktop app, with no CLI login. A haiku ping took about 0.9 s. A full judgment took about 5 s and returned a real FLAG on a recorded turn. The call returns `{isAnswered, text, usage}`. In the mod, an expired CLI login does not silence the watch.

## Review rounds

- Try 1 is 386194a. Review round 1 failed.
- Try 2 is 02120a9. Review round 2 failed: a config notice did not show (F1, with the 00:09 arbiter ruling), the python calls had no mod timer (F2), and the wording named a "real Stop hook" that is gone (F4).
- Try 3 fixes F1, F2 and F4.

## What protects it

`mods/decision-watch/decision-watch.test.mjs`. Pin commits: cc9bdd2 and 31089ce.

## Unverified

- Whether `classic.Stop` reaches a mod in the desktop app. The spike's log holds no Stop line.
- How long `$` lives after `classic.Stop` returns, when the background call is `void shadow`.
- Whether the host stops a model call at `timeoutMs`. The field is not in `ModelCompleteRequest`, so the mod enforces 50 s itself with a timer race that fails the step and frees the slot.
- Whether `$.process.run` kills the child at `timeoutMs`. The mod's timer frees the slot, but it does not kill the child.
- The exit code of `where.exe python3 python` when only `python` exists.

## Holes, named

Debts: `dw-slash-cache-hit-reads-clean` (a /dw cache hit reads like a clean turn, and Stops seen caps at 500), `dw-log-write-failures-silent` (a lost log write is silent), `dw-slot-timers-unmeasured` (the slot timers are computed, not measured), `dw-log-keeps-model-text` (the log keeps model text that may hold a secret), `dw-where-exe-both-phases` (pickPython runs where.exe in both phases), `dw-stop-row-unproven` (the Stop row drop is unproven live), `dw-busy-stop-skipped` (a Stop during a judge is never judged), `dw-notice-lead-space-lost` (the log drops a notice's leading whitespace).
## Named limits

- HOLE 7: a bad flag combination on `decision_watch.py` makes the script use `invoke_model` instead, which can start a 120 s `claude -p` call. The fallback is pinned on purpose.

## Deferred, not built

`guard_core._force_utf8_streams` should also reconfigure stdin. Without it, the script reads raw non-ASCII stdin wrongly on Windows, and the mod's escape would then be redundant. This belongs to the guard lane. No lane owns it yet.

Kind: process
Home: mods/decision-watch/hooks/register.mjs
