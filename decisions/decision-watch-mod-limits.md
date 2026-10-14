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

- HOLE 1, closed. Phase 1 prints a `key`. The mod gives it back to phase 2 as `--key` after the reply. A key the live evidence no longer gives reads UNKNOWN, and so does a phase 1 with no key.
- HOLE 2. A new human message between the phases moves the baseline. A real FLAG then prints `verdict lost`. The output is loud and correct, but the README named one cause only. Fix: the README now names this cause.
- HOLE 3. `/dw` prints `nothing to say (no protected change, no model call)` on a cache hit too. A second `/dw` after a FLAG reads like a clean turn. No fix is named.
- HOLE 4. The log is the only output for an ALLOW, and the toast shows a FLAG or UNKNOWN too. A lost log write is silent: an empty catch and a 2 s cap, so START may have no END. Any read error resets the log to one line. Whether `$.fs.write` is atomic is unverified. No fix is named.
- HOLE 5. Each step that holds the slot has a mod timer: each python finder 6 s (two per run), each python run 31 s (a 30 s host limit, unmeasured against a real run), the model call 50 s, each toast 5 s (a verdict and up to three notices), each log write 2 s (up to six). The sum is about 168 s, computed, not measured. A timer frees the slot but does not stop the host call or kill the child. The `$.env.get` reads have no timer. No fix is named.
- HOLE 6. The log keeps the FLAG `why` up to 2000 characters. That text is model words about a diff, and it may quote a secret. The log also keeps the first 200 characters of non-JSON phase-1 output, which is fixed prompt text only. No fix is named.
- HOLE 7. A bad flag combination on `decision_watch.py` makes the script use `invoke_model` instead. That can start a 120 s `claude -p` call. Fix: none. The fallback is pinned on purpose.
- HOLE 8. `Stops seen` counts only lines still in the 500-line log, so N is at most 500. A second `/dw` on the same turn says `nothing to say`, because `/dw` keeps its own cache. No fix is named.
- HOLE 9 (minor). `textOf` drops `r.reason`, so an aborted call reads `no text`. The `asciiJson` regex holds a literal U+FFFF character. `pickPython` runs `where.exe` in both phases. No fix is named.
- HOLE 10. The Stop row is removed, but it is unproven live that `classic.Stop` reaches a mod in the desktop app. The drop is unproven until the mod log shows `STOP seen` lines after merge. The orchestrator measures that and restores the Stop row if none show.
- HOLE 11. A Stop that lands while a judge runs is skipped (`SKIP busy`). `decision_watch.py` scopes a turn by file time after the last human message, so for a new turn that Stop is never judged: the next Stop of that turn judges it only if one comes. No fix is named.

## Deferred, not built

`guard_core._force_utf8_streams` should also reconfigure stdin. Without it, the script reads raw non-ASCII stdin wrongly on Windows, and the mod's escape would then be redundant. This belongs to the guard lane. No lane owns it yet.

Enabling: the plugin key for this mod is not set. Four other mods are on (owner 2026-10-12 12:22 CDT). The owner has not yet ruled on this one.

Kind: process
Home: mods/decision-watch/hooks/register.mjs
