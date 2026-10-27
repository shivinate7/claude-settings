# decision-watch

A mod. It runs the decision watch on each completed turn (`turn.complete`) with this session's own model login. It replaces the Stop hook row. It never refuses a turn. A FLAG or UNKNOWN verdict shows in the session as a toast. An ALLOW verdict shows nothing. Each config notice shows as its own toast, marked `Decision watch notice:`.

## What it does

- On each main-loop turn (`turn.complete`), the mod finds the transcript from the session id, read on each turn, and the cwd. The lookup waits at most 0.5 s and runs in the background. A lookup that passes the limit, or an id that cannot be read, logs a SKIP line and judges nothing.
- It writes one "STOP seen" line to the log. The handler waits at most 500 ms for that line, then returns the turn. The judging runs in the background.
- An agent turn (`agentId` set) is skipped. A turn with `isAborted` set, or a reason other than `answer`, is skipped with a SKIP line. A turn with no transcript logs a SKIP line.
- One judge runs at a time. A turn that arrives during a judge logs "SKIP busy" and does not judge.
- The judging uses `hooks/decision_watch.py` in your Claude config folder, in two steps.
  1. `--emit-prompt` runs the cheap path. It prints a prompt only when a model call is due.
  2. The mod calls the model with that prompt. The mod enforces a 50 s limit itself (a timer races the call). A call that passes it reads as a model error. Then `--model-text` or `--model-error` gives the verdict.
- Each python run (30 s) and each finder call (5 s, one name) also has a mod timer: the host limit plus 1 s. A run that passes it reads UNKNOWN. A toast has a 5 s timer. A hung python, model or toast call frees the one-judge slot. The `$.env.get` reads have no timer.
- Every failure reads as UNKNOWN. A failure never reads as ALLOW.
- Phase 1 prints a `key` for the evidence it judged. The mod gives it back to phase 2 as `--key` after the reply. Evidence that moved between the two steps reads UNKNOWN. A phase 1 with no key reads UNKNOWN.
- Under the split flags, the script prints `verdict` and `notices` as separate JSON fields. The mod does not parse joined text.
- The verdict toast holds the script's own FLAG or UNKNOWN message, or the mod's own UNKNOWN text. Each notice (config files, merges into main, unread subjects) gets its own toast. Each notice is logged on its own `NOTICE` line or lines before the END line, which holds the verdict only. A verdict that is neither FLAG nor UNKNOWN is logged as `NOT SHOWN`. A failed toast is logged as `TOAST FAILED`, with the text it failed to show.
- A model verdict that the script cannot use reads as "verdict lost". This happens when another judge already recorded the same turn. The script prints this marker whenever it gets a model reply and ends before the model step. A valid ALLOW that the script uses stays ALLOW.
- A new human message between the two steps also causes it. The baseline moves, so a real FLAG can print "verdict lost". That is loud and correct.
- The mod sends the Stop JSON to python as ASCII only. It escapes each other character as `\uXXXX`.

## Log

- The log is `shadow.log` (the file name is kept) in the state folder `decision-watch-shadow`, inside the config folder.
- Each judged turn has a START line and an END line. The END line holds the timings and the verdict line. The log never holds the prompt.
- The log keeps the newest 500 lines. A line is cut at 2000 characters.
- Writes go one at a time. The host writes the folder if it is missing.
- If the host refuses to read a log that is too big, the log starts over with the new line.
- A log write waits at most 2 s. A late write can be lost.

## Where things live

- The script path is `CLAUDE_CONFIG_DIR/hooks/decision_watch.py`. With no `CLAUDE_CONFIG_DIR`, the mod uses `USERPROFILE` or `HOME`, then `.claude`.
- The background judge and `/dw` each have their own state folder: `decision-watch-shadow` and `decision-watch-dw`. Each holds its own "already judged" cache. A background verdict does not mute `/dw`.
- The mod picks the first `python3` or `python` on PATH that is not the Windows Store stub. It asks the finder for one name at a time, because `which` and `where.exe` exit 1 when any name is missing, and a Mac has no `python`. It keeps that path until the mod reloads, and looks again after a run with it is rejected, times out, or exits non-zero with the file gone.

## /dw

The command runs the same judgment on the latest turn. It shows the timings, the result and each notice. It never shows the prompt. Before the first judged turn, it finds the transcript from the session id.

The last line is "Stops seen: N". N counts the STOP seen lines now in the log. The log keeps 500 lines, so N is at most 500.

`/dw` has its own cache. Run on the same turn twice, the second run says "nothing to say".

## Unknown

- Whether the desktop app and the terminal both give the model call the same login.
- Whether `$.model.complete` stops at `timeoutMs`. The request field is not in the host's type, so the mod does not rely on it. Its own timer enforces the 50 s limit. The host call may keep running after the timer.
- Whether `$.process.run` kills the child at `timeoutMs`. The mod's timer frees the slot, but it does not kill the child. A hung python may keep running.

## Limits

- The script must be the version that knows `--emit-prompt`, `--model-text`, and `--model-error`.
- A bad flag combination on the script falls back to the normal `claude -p` call. This is a known limit: a wrong flag from a caller runs the old path.
- A turn that arrives during a judge is skipped. The script scopes a turn by the file time after the last human message. So a new turn that lands during a judge is never judged.
- The ruling and what is unverified: `decision-watch-mod-limits` (limits of the mod).

## Try in the desktop app

Refresh the installed `~/.claude/hooks/decision_watch.py` first. Replace it with this repo's `hooks/decision_watch.py`. An old copy ignores `--emit-prompt`, so each turn runs `claude -p`.

1. Install: `/plugin install decision-watch --marketplace shivinate7/claude-settings`, then restart the session.
2. Finish a turn. Run `/dw`. Check that the last line counts the turn.

## Check

- `node mods/decision-watch/decision-watch.test.mjs` runs the tests (stdlib only).
- `claude plugin validate mods/decision-watch` checks the mod.
- Try it: `claude --plugin-dir mods/decision-watch`, then `/dw`.
