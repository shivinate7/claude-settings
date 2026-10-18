# A background server or watcher needs an end condition at start

## The ruling

Owner, 2026-10-13 23:41 CDT: "End condition at start."

- A Bash or PowerShell call with `run_in_background` that starts a server or a watcher needs a note in its `description`: `until: <condition>`.
- The guard rule `background-end` in `hooks/guard_stream.py` refuses the call when the note is missing or its condition is empty.
- The Stop check (`stall_watch --stop`) shows each quiet job's note beside it. The agent judges whether the job should still run.
- One-off builds and test runs pass without the note. `gh run watch` is refused (`ci-wait-reads-run-status`, CI waits read the run status).
- The roster, as built:
  - Script runners npm, pnpm, yarn and bun: the script name counts when a part of it, split on `:` and `-`, is dev, serve, start, watch or preview. `build:watch` and `start-api` count; `build` and `build-docs` do not. A binary run through `exec`, `dlx` or `x` is not a script name. `deno task <script>` uses the same rule.
  - `--watch` or `--watch=<v>` counts on any tool except `gh`, whose watchers end with the run. `--watch=false`, `--watch=0`, `--watch false` and `--watch 0` do not count. `bun --hot` counts.
  - Programs (`SERVER_PROGRAMS`): serve, http-server, live-server, nodemon, uvicorn, http.server.
  - Programs by verb (`SERVER_VERBS`, first positional word): next dev or start, deno serve, jupyter lab or notebook, webpack serve, astro dev, rails s or server, streamlit run.
  - `flask run` (also `flask --app <name> run`), `vite` without `build`, and `tsc -w`.
  - `python -m <module>` reads the module as the program, such as `python -m http.server`.
  - The guard reads through `cmd /c`, `bash -c`, `pwsh -Command`, `&`, a subshell, `.cmd` and `.exe` names, and `npx pkg@version`.

Why: a server or watcher can run long after its work ends, and nothing in the start call says when it stops. No background job should run unattended for a day with no stated reason.

Kind: process
Home: hooks/guard_stream.py
Home: hooks/stall_watch.py
