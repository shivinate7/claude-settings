# session-board

A mod. It adds two commands. `/board` shows the local sessions and agents and what each one is doing. `/safe-stop` checks that a session has no running work before you stop it. It also refuses a question box while the session's own work runs. It draws nothing else. It calls no model.

## /board

The command opens a pane with two levels.

All sessions: one band, then one row per session.

- The band reads like "5 working, 2 waiting, update-ready 6 of 8".
- A row shows repo, branch, state, update mark, context percent, and running agents.
- State is "working", "waiting", or "permission". "Permission" means that a tool check returned "ask" and its tool call has not returned yet. An approved long tool call keeps the label until the call ends.
- The update mark is "ready", "not ready", "unknown", or "no detail".
- Press a row, or its number, to open that session.
- The pane shows 40 rows. A line says how many more exist. The count includes entries the board did not read.

One session: agents with status, the last 5 tool calls, files touched, context percent, permission checks, and a receipt for the last turn.

`/board text` prints the same board as plain text. Use it where no pane shows.

## Update-ready

A session is update-ready when all five hold: no running agents, state is waiting, no permission ask, no unpushed commits, and a clean tree.

- Running servers and background tasks are not part of it. A session with a dev server can read "ready".
- The git counts come from a reading at turn end and on attach. While the session waits, the heartbeat reads git again 5 minutes after the last read, one read at a time. A session at work reads git only at turn end.
- A failed or hung git read waits the same 5 minutes before the next one.
- A read that began before the latest turn start is dropped when it lands.
- A reading older than 330 s is "unknown". A failed or slow git call is "unknown". A branch with no upstream is "unknown". Unknown is never ready.
- The 330 s rule (5 minutes plus one beat) guards against a stuck reader, not against idleness.

## Where the data comes from

- `claude agents --json` seeds the list. One call per refresh, 8 s timeout. A session without this mod shows as "no detail".
- Each session with the mod writes `sess:<sessionId>` to `$.store`. The entry holds repo folder name, branch, and state. It also holds the git counts with their reading time, and the running agent count. It holds spawn counts by agent type, the context percent, and a time stamp. It stays under 1 KB.
- It also writes `detail:<sessionId>`, under about 3 KB, for the one-session view. The mod writes it again only when its content changes.
- A heartbeat refreshes the entry every 30 s. The board hides an entry older than 2 minutes, or stamped more than 30 s ahead of now. The session removes both records at session end. A killed session leaves them. The 2-minute rule hides them. An entry older than one day is deleted at the next session start or `/board`, unless `claude agents` lists that session as live. If the list is not available, nothing is deleted.
- The board reads the 200 newest entries. It says how many more exist.
- After `/clear` or a resume, the mod writes nothing for the old id and reads the id again on each beat. It writes under the new id when that binds. After session end it writes nothing.
- The git call runs once per turn end, once per attach and once per 5 idle minutes: argv array, no shell, `core.fsmonitor=false`, `--no-optional-locks`, 5 s timeout.
- These steps each wait at most 100 ms for their git, agent, context, and store work: session start, turn start, turn end, a permission ask, and the end of a tool call. The work then finishes on its own.
- The 100 ms wait does not cover everything. At session start, `$.session.repo()` and `$.command.register()` are not bounded by it. At session end, the store deletes are not bounded by it. On `/clear` or a resume, `$.session.repo()` is not bounded either.
- A permission ask with no tool id writes nothing.
- The pane refreshes the board on the heartbeat while it is open. It stops when the pane closes, or after 10 refreshes with no `/board` call.

## Privacy

- The store is on this machine and is read by this machine only.
- The mod stores no prompt text, no file content, and no folder path. It shows the repo folder name and the branch.
- The recent list names a file only for the file tools: Read, Edit, Write, MultiEdit, NotebookEdit, Glob, and Grep. It stores the file name, never the folder. A Bash command and an MCP tool give the tool name only.
- A name that looks secret shows as "(secret file)". The rule is the one in `mods/plain-diff`. Examples are `.env`, `*.pem`, `id_rsa`, and `credentials.json`. `.env.example` and `credentials.ts` keep their names.
- A Grep or Glob path shows only when its last part has an extension. A folder named like a file still shows. That is a known limit.
- Names on the board are plain text. Control characters, bidi marks, and the characters `< > & " backtick` are removed or replaced. Long names are cut. The mod reads store values back through the same check.
- The mod shows no cost figure. The cost figure is not reliable.

## /safe-stop

It asks this session to reach a stopping point and write its handoff.

1. It runs the installed handoff hook's own path functions (`hooks/precompact_handoff.py`, through `python3` or `python`). It gets the handoff path and the prompt file path. This makes the handoff folder if it is missing.
2. It sends this session one prompt. The prompt says: finish the step, start no new work, and follow the hook's prompt file. It also says: rewrite the handoff whole, then report branch, uncommitted files, unpushed commits, and running agents.

The prompt is queued until the session is idle. The reply says so. If the host rejects the prompt, the reply says "could not send".

The mod writes no handoff. The session does, by the hook's own rules.

`/safe-stop plan` prints the prompt and sends nothing. If python or the hook is missing, `/safe-stop` prints what is missing and sends nothing.

The origin check is a refusal list. A run from a plugin, a peer session, a coordinator, a schedule, or an auto-continuation is refused. Other origins run, such as `unclassified`, `sdk`, and `bridge`. The check does not prove that a person typed the command.

The python call runs with `-I` and with the config folder as its working directory, never the session folder. A repo file named `json.py` cannot run. A path over 4000 characters is refused, not cut.

## Unknown

- Whether turn end fires while a session waits on a permission prompt. Headless mode cannot test it. The mod uses a tool check that returns "ask" as the waiting signal. An auto-approve mode can answer an "ask" with no person.
- The order of hooks in the desktop app. The mod clears a permission ask after the tool call returns. This assumes that the host runs the permission check inside the tool call. A headless run did not confirm it.
- Whether the pane draws well in the desktop app. Only a terminal or the app can show it. Headless runs cannot.
- Whether `$.process` works in the desktop app. The API says "CLI only". If it fails there, branch, readiness, and the `claude agents` seed are missing. The board then shows store entries alone, and no session is ready.
- Whether the app and the terminal share one store. Same config folder should do it.
- Whether a prompt sent from a command starts a turn in the desktop app (`/safe-stop`).
- The time of the git call in the biggest repo. In the q_max clone, one run took 0.11 s with a warm cache. That is one run on one machine. The real per-turn cost is not measured.
- Context percent reads 0 in a headless `-p` run.

Checked: the session id in `claude agents --json` equals the id the mod writes. Two live sessions merged into one row each.

## Limits

- A session without the mod shows on the board as "no detail", from the agents list. It shows repo and state only. It gets full detail after it loads the mod.
- The store file name carries the install: a `--plugin-dir` run wrote `session-board_inline-<hash>.json`. Sessions loaded two ways probably do not share one file. Load every session the same way.
- The running agent count is as of the last turn end or heartbeat. It can lag by 30 s.
- A denied permission clears when the tool call returns, the same as an approved one. Turn end also clears it.
- Known limit, the sweep: it deletes day-old records only when `claude agents --json` gives a valid JSON list. A banner line, an object, or no output deletes nothing. A valid empty list `[]` counts as real, so day-old records of sessions with no live row go.
- Known limit, the clear race: after `/clear` or a resume, a store write already held at the host can land late. The mod removes it again after it lands. The old entry can show for a short moment.
- Known limit, the idle git read: the tree can change between reads, so a clean tree can read as clean for up to 5 minutes after an edit made outside the session. A turn end reads again.
- Known limit, the config folder: under Git Bash, `HOME` is a path like `/c/Users/x`. `/safe-stop` uses `USERPROFILE` first when it starts with a drive letter. Another setup can pick the wrong folder. Set `CLAUDE_CONFIG_DIR` to be sure.
- A mod error is not shown in the session. It goes to the debug log (`claude --debug`), one line starting "session-board:".

## Try in the desktop app

1. Install: `/plugin install session-board --marketplace shivinate7/claude-settings`, then restart the session.
2. Run `/board`. Check that the pane draws, that rows open, and that a session without the mod shows "no detail".
3. Start a long turn in a second session. Check that its row reads "working", then "waiting" at the end.
4. Trigger a permission prompt. Check that the row reads "permission".
5. Run `/safe-stop plan`, then `/safe-stop`. Check that the handoff file changes.

## Check

- `node mods/session-board/session-board.test.mjs` runs the tests (stdlib only).
- `claude plugin validate mods/session-board` checks the mod.
- Try it: `claude --plugin-dir mods/session-board`, then `/board`.

## The question-box check

AskUserQuestion is refused while an agent, a background command or a workflow of this session runs. It is also refused for the rest of the session once the session has started another session. A box stops the session until the owner answers, and the running work and the started sessions wait or go on with no brake.

- Agents come from the host's agent list, read once per box. Background commands and workflows are the ones the mod saw start and not yet end. A monitor does not count. The engine's list at each turn end resets them.
- A start is a desktop `start_session` or cloud `create_session` call that answers without error. A start inside a subagent counts too; a Routine does not. The count lives in the store key `started:<id>`, so it survives a mod reload and a restart or resume under the same id. A `/clear` carries it; an in-process resume takes the resumed session's own count.
- The refusal says to ask in the reply and on the waiting page, then keep working.
- An unreadable agent list lets the box through, and the debug log and `guard.log` say unknown.
- Each refusal writes one `guard.log` line through `hooks/guard_core.py`, rule `question-box-while-work`.
