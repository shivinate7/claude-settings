# decision-watch

A mod. It runs the Stop-time decision watch with this session's own model login. It replaces the Stop hook row. It never blocks a turn. A FLAG or UNKNOWN shows in the session as a toast, with the text the Stop hook showed. An ALLOW shows nothing.

## What it does

- On every Stop, the mod writes one "STOP seen" line to the log. It waits at most 0.5 s for that write. Then it returns at once.
- It then judges the turn in the background. It skips the judge when `stop_hook_active` is set.
- One shadow judge runs at a time. A Stop that arrives during a judge logs "SKIP busy" and does not judge.
- The judging uses `hooks/decision_watch.py` in your Claude config folder, in two steps.
  1. `--emit-prompt` runs the cheap path. It prints a prompt only when a model call is due.
  2. The mod calls the model with that prompt. The call has a 50 s limit. Then `--model-text` or `--model-error` gives the verdict.
- Every failure reads as UNKNOWN. A failure never reads as ALLOW.
- Phase 1 prints a `key` for the evidence it judged. The mod gives it back to phase 2 as `--key` after the reply. Evidence that moved between the two steps reads UNKNOWN. A phase 1 with no key reads UNKNOWN.
- The toast holds the script's own message, or the mod's own UNKNOWN text. The log holds the same verdict.
- A model verdict that the script cannot use reads as "verdict lost". This happens when another judge already recorded the same turn. The script prints this marker whenever it gets a model reply and ends before the model step. A valid ALLOW that the script uses stays ALLOW.
- A new human message between the two steps also causes it. The baseline moves, so a real FLAG can print "verdict lost". That is loud and correct.
- The mod sends the Stop JSON to python as ASCII only. It escapes each other character as `\uXXXX`.

## Log

- The log is `shadow.log` in the state folder `decision-watch-shadow`, inside the config folder.
- Each judged Stop has a START line and an END line. The END line holds the timings and the verdict line. The log never holds the prompt.
- The log keeps the newest 500 lines. A line is cut at 2000 characters.
- Writes go one at a time. The host writes the folder if it is missing.
- If the host refuses to read a log that is too big, the log starts over with the new line.
- A log write waits at most 2 s. A late write can be lost.

## Where things live

- The script path is `CLAUDE_CONFIG_DIR/hooks/decision_watch.py`. With no `CLAUDE_CONFIG_DIR`, the mod uses `USERPROFILE` or `HOME`, then `.claude`.
- The shadow judge and `/dw` each have their own state folder: `decision-watch-shadow` and `decision-watch-dw`. Neither is the real config folder. The real Stop hook keeps its own "already judged" cache and the mod never touches it. A shadow verdict does not mute `/dw`.
- The mod picks the first `python3` or `python` on PATH that is not the Windows Store stub.

## /dw

The command runs the same judgment on the latest turn. It shows the timings and the result. It never shows the prompt. Before the first Stop, it finds the transcript from the session id.

The last line is "Stops seen: N". N counts the STOP seen lines now in the log. The log keeps 500 lines, so N is at most 500.

`/dw` has its own cache. Run on the same turn twice, the second run says "nothing to say".

## Unknown

- Whether the desktop app and the terminal both give the model call the same login.
- Whether `$.model.complete` stops at `timeoutMs`. The mod also sets one judge at a time, so a hung call holds the slot.

## Limits

- The script must be the version that knows `--emit-prompt`, `--model-text`, and `--model-error`.
- A bad flag combination on the script falls back to the normal `claude -p` call. This is a hole: a wrong flag from a caller runs the old path.
- A Stop that arrives during a judge is not judged. The next Stop on an unchanged turn judges it.
- The ruling and the holes: `decision-watch-mod-limits` (limits of the mod).

## Try in the desktop app

Refresh the installed `~/.claude/hooks/decision_watch.py` first. Replace it with this repo's `hooks/decision_watch.py`. An old copy ignores `--emit-prompt`, so each Stop runs `claude -p`.

1. Install: `/plugin install decision-watch --marketplace shivinate7/claude-settings`, then restart the session.
2. Finish a turn. Run `/dw`. Check that the last line counts the Stop.

## Check

- `node mods/decision-watch/decision-watch.test.mjs` runs the tests (stdlib only).
- `claude plugin validate mods/decision-watch` checks the mod.
- Try it: `claude --plugin-dir mods/decision-watch`, then `/dw`.
