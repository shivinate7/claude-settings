# session-board

A mod. It adds two commands, `/board` and `/safe-stop`. It draws nothing else. It calls no model.

## /board

The command opens a pane with two levels.

All sessions: one band, then one row per session.

- The band reads like "5 working, 2 waiting, update-ready 6 of 8".
- A row shows repo, branch, state, update mark, context percent, and running agents.
- State is "working", "waiting", or "permission". "Permission" means that a tool check came back "ask" and the call has not started yet.
- Press a row, or its number, to open that session.

One session: agents with status, the last 5 tool calls (tool name and file name only), files touched, context percent, permission checks, and a receipt for the last turn.

`/board text` prints the same board as plain text. Use it where no pane shows.

A session is update-ready when all four hold: no running agents, state is waiting, no unpushed commits, and a clean tree. An unknown value is never ready.

## Where the data comes from

- `claude agents --json` seeds the list. One call per refresh, 10 s timeout. A session without this mod shows as "no detail".
- Each session with the mod writes `sess:<sessionId>` to `$.store`. The entry holds repo folder name, branch, and state. It also holds the uncommitted file count, the unpushed commit count, and the running agent count. It holds spawn counts by agent type, the context percent, and a time stamp. It stays under 1 KB.
- It also writes `detail:<sessionId>`, under about 3 KB, for the one-session view.
- A heartbeat refreshes both every 30 s. The board hides an entry older than 2 minutes. The session removes both at session end. A killed session leaves them. The 2-minute rule hides them. An entry older than one day is deleted at the next session start or `/board`.
- Readiness comes from one `git status` call per turn: argv array, no shell, `core.fsmonitor=false`, `--no-optional-locks`, 5 s timeout.

## Privacy

- The store is on this machine and is read by this machine only.
- The mod stores no prompt text, no file content, and no path. It shows the repo folder name and the branch. The one-session view also shows file names.
- A Bash command is never stored. Only the tool name is.
- Anything shown is plain text. Control characters, bidi marks, and the characters `< > & " backtick` are removed or replaced. Long names are cut. The mod reads store values back through the same check.
- The mod shows no cost figure. The cost figure is not reliable.

## /safe-stop

It asks this session to reach a stopping point and write its handoff.

1. It runs the installed handoff hook's own path functions (`hooks/precompact_handoff.py`, through `python3` or `python`). It gets the handoff path and the prompt file path. This makes the handoff folder if it is missing.
2. It sends this session one prompt. The prompt says: finish the step, start no new work, and follow the hook's prompt file. It also says: rewrite the handoff whole, then report branch, uncommitted files, unpushed commits, and running agents.

The mod writes no handoff. The session does, by the hook's own rules.

`/safe-stop plan` prints the prompt and sends nothing. If python or the hook is missing, `/safe-stop` prints what is missing and sends nothing.

## Unknown

- Whether turn end fires while a session waits on a permission prompt. Headless mode cannot test it. The mod uses a tool check that returns "ask" as the waiting signal. The check runs before the prompt. An auto-approve mode can answer an "ask" with no person. A rejected prompt keeps "permission" until the turn ends.
- Whether the pane draws well in the desktop app. Only a terminal or the app can show it. Headless runs cannot.
- Whether `$.process` works in the desktop app. The API says "CLI only". If it fails there, branch, readiness, and the `claude agents` seed are missing. The board then shows store entries alone, and a session with no git reading is never update-ready.
- Whether the app and the terminal share one store. Same config folder should do it.
- Whether the session id in `claude agents --json` equals the id the mod writes. The merge joins on it. A headless run did not confirm it. If they differ, each session shows twice: once as "no detail", once from the store.
- Whether a prompt sent from a command starts a turn in the desktop app (`/safe-stop`).
- Context percent reads 0 in a headless `-p` run.

## Limits

- A session that started before the install does not appear until it restarts.
- A session without the mod shows repo and state only.
- The store file name carries the install: a `--plugin-dir` run wrote `session-board_inline-<hash>.json`. Sessions loaded two ways probably do not share one file. Load every session the same way.
- A branch with no upstream gives "unpushed: unknown". The session is not update-ready.
- The running agent count is as of the last turn end or heartbeat. It can lag by 30 s.
- A mod error is not shown in the session. It goes to the debug log (`claude --debug`), one line starting "session-board:".

## Try in the desktop app

1. Install: `/plugin install session-board --marketplace shivinate7/claude-settings`, then restart the session.
2. Run `/board`. Check that the pane draws, that rows open, and that a session without the mod shows "no detail".
3. Start a long turn in a second session. Check that its row reads "working", then "waiting" at the end.
4. Trigger a permission prompt. Check that the row reads "permission".
5. Run `/safe-stop plan`, then `/safe-stop`. Check that the handoff file changes.

## Check

- `claude plugin validate mods/session-board` checks the mod.
- Try it: `claude --plugin-dir mods/session-board`, then `/board`.
