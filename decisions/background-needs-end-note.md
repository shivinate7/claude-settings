# A background server or watcher needs an end condition at start

## The question

How does a background server or watcher stop when its work ends?

## The incident

A q_max file server ran on port 3202 for 27 h. It was quiet for 99,352 s. No check stopped it.
The Stop quiet-shell check (`stall_watch --stop`, the Stop check, live since 2026-10-13 16:28)
caught it on its first chance.

## The ruling

Owner ruling, 2026-10-13 23:41 CDT: "End condition at start."

- A Bash or PowerShell call with `run_in_background` that starts a server or a watcher needs a
  note in its `description`: `until: <condition>`.
- The guard rule `background-end` in `hooks/guard_stream.py` refuses the call when the note is
  missing, or when its condition is empty.
- The roster is named. As built:
  - Script runners npm, pnpm, yarn and bun: the script name counts when a part of it, split on
    `:` and `-`, is dev, serve, start, watch or preview. `build:watch`, `dev-server` and
    `start-api` count; `build` and `build-docs` do not. A binary run through `exec`, `dlx` or `x`
    is not a script name. `deno task <script>` uses the same name rule.
  - `--watch` or `--watch=<v>` counts on any tool except `gh`, whose watchers end with the run.
    `--watch=false`, `--watch=0`, `--watch false` and `--watch 0` do not count. `bun --hot`
    counts.
  - Programs (`SERVER_PROGRAMS`): serve, http-server, live-server, nodemon, uvicorn,
    http.server.
  - Programs by verb (`SERVER_VERBS`, first positional word): next dev or start, deno serve,
    jupyter lab or notebook, webpack serve, astro dev, rails s or server, streamlit run.
  - `flask run` (also `flask --app <name> run`), `vite` without `build`, and `tsc -w`.
  - `python -m <module>` reads the module as the program: `python -m http.server`,
    `python -m flask run`, `python -m uvicorn`, `python -m streamlit run`.
  - The guard reads through `cmd /c`, `bash -c`, `pwsh -Command`, `&`, a subshell, `.cmd` and
    `.exe` names, and `npx pkg@version`.
- One-off builds, test runs and `gh run watch` pass without the note.
- The Stop check shows each quiet job's note beside it. The agent judges whether the job should
  still run.

## Why

A server or watcher can run long after its work ends. Nothing in the start call says when it
stops. A note at start gives the Stop check a condition to show. The protected outcome: no
background job runs unattended for a day with no stated reason.

## What protects it

- The guard refuses the call at start (rule `background-end`).
- The Stop check shows the note of each quiet job at turn end.

## Holes, named

Debts: `timeout-moved-server-unchecked` (a foreground server moved to background at 120 s is not checked), `node-file-server-unchecked` (a background `node server.js` is not refused), `until-note-unjudged` (the note is checked for presence only), `server-wrappers-unread` (a server behind some wrappers and forms is not refused), `bg-end-false-alarms` (script names and flask or jupyter commands are refused), `bg-end-roster-gaps` (watch flags and servers outside the roster pass, and a `nohup x &` call is left to the detached-launch rule).

Kind: process
Home: hooks/guard_stream.py
Home: hooks/stall_watch.py
