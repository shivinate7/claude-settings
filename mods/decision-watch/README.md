# decision-watch

A mod. It runs the Stop-time decision watch with this session's own model login. It runs in shadow mode only. It never blocks a turn and never shows a message in the session.

## What it does

- On every Stop, the mod returns at once. It then judges the turn in the background.
- It skips a Stop that has `stop_hook_active` set.
- The judging uses `hooks/decision_watch.py` in your Claude config folder, in two steps.
  1. `--emit-prompt` runs the cheap path. It prints a prompt only when a model call is due.
  2. The mod calls the model with that prompt. Then `--model-text` or `--model-error` gives the verdict.
- Every failure reads as UNKNOWN. A failure never reads as ALLOW.
- The log holds one START line and one END line for each judged Stop. The END line holds the timings and the verdict line. The log never holds the prompt.

## Where things live

- The script path is `CLAUDE_CONFIG_DIR/hooks/decision_watch.py`. With no `CLAUDE_CONFIG_DIR`, the mod uses `USERPROFILE` or `HOME`, then `.claude`.
- The mod gives the script its own state folder, `decision-watch-mod`, inside the config folder. The real Stop hook keeps its own "already judged" cache and the mod never touches it.
- The log is `shadow.log` in that state folder.
- The mod picks the first `python3` or `python` on PATH that is not the Windows Store stub.

## /dw

The command runs the same judgment on the latest turn. It shows the timings and the result. It never shows the prompt. Before the first Stop, it finds the transcript from the session id.

## Unknown

- Whether `$.fs.write` makes a missing folder. The mod calls `$.fs.mkdir` only when the host has it. If neither works, the mod writes no log and shadow mode shows nothing.
- Whether the desktop app and the terminal both give the model call the same login.

## Limits

- The script must be the version that knows `--emit-prompt`, `--model-text`, and `--model-error`.
- A bad flag combination on the script falls back to the normal `claude -p` call. This is a hole: a wrong flag from a caller runs the old path.
- Two Stops that end close together can write the log at the same time. One line can then be lost.

## Check

- `node mods/decision-watch/decision-watch.test.mjs` runs the tests (stdlib only).
- `claude plugin validate mods/decision-watch` checks the mod.
- Try it: `claude --plugin-dir mods/decision-watch`, then `/dw`.
