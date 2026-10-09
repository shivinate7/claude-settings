# Each question passes an outcome check before the owner sees it

## The problem

The owner often answers a question with options by asking: "Are these options aimed at
the outcome, or do they miss the point?" The next question then has the right options.
The trial `AskUserQuestion` prompt hook (decision haiku-prompt-hooks) cannot catch this. A
prompt hook sees only the question, never the chat, so it judges form alone.

## The ruling

Owner rulings, 2026-10-08:
- Each question opens with one line, `You want: <the goal>`, in the owner's terms. The
  owner sees at a glance whether the goal was read right.
- A command hook, `hooks/question_outcome.py`, runs on PreToolUse for `AskUserQuestion`.
  It reads the owner's last messages from `transcript_path`. It asks a model whether the
  `You want:` line matches those messages, and whether each option serves that goal. It
  also asks whether an option that serves the goal better is missing.
- The model call reuses `invoke_model` from `hooks/decision_watch.py`. The model is Haiku
  at effort `xhigh`.
- `invoke_model` starts a second `claude` program. That program does not share the app's
  login. Its login file expired on 2026-09-23 and never renewed, because the call works
  on a copy of the file and throws the copy away. So neither hook got a verdict (measured
  2026-10-08).
- Owner ruling, 2026-10-08: both hooks log in with a one-year token from
  `claude setup-token`. The owner saves it in `~/.claude/state/hook-token`, on each
  machine. `invoke_model` reads that file and passes the token to the call as
  `CLAUDE_CODE_OAUTH_TOKEN`. A file works the same on Windows and macOS, needs no app
  restart, and is never in the repository. With no token file, the call keeps today's
  path. The file may be saved as UTF-8 (with or without a BOM) or as UTF-16.
  Accepted risk: the guard blocks writes to `~/.claude/state`, but not reads, so a session
  can print the token into its transcript. `.credentials.json` carries the same risk
  today.
- An in-app agent hook was weighed and set aside. It cannot run `git`, which
  `decision_watch` needs. In the app's `auto` permission mode it could not open the
  transcript (about 60 "Unable to verify" answers, measured for the old decision_watch
  agent hook).
- On a miss, the hook denies the call. The reason goes back to the session, which fixes
  the question before the owner sees it.

## Bounds

- A clarifying question, with no options or one option, passes first.
- Any other question with no `You want:` line, or an empty one, is denied with no model
  call.
- The hook reads only the owner's own messages from the last 2 MiB of the transcript.
  Task notifications, hook feedback, peer messages and tool results are not the owner's.
- A model call that fails or times out lets the question through, and the hook prints
  one line that says so. That line never repeats the prompt. A question is not a
  destructive act, so a lost check costs less than a blocked question.
- After a deny, the next question in the session passes with no model call, whatever
  its text. That clears the state. A deny state older than 30 minutes is ignored. If the
  hook cannot record or clear a deny, it does not deny, and it says the check did not run.
  So a judge that is wrong cannot loop.
- The reason sent back to the session is capped and cleaned.
