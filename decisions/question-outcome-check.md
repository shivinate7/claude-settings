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
- Two hooks run on PreToolUse for `AskUserQuestion`:
  - A command hook, `hooks/question_outcome.py`, makes the checks that need no model.
  - An agent hook (`type: agent`, Haiku) judges the outcome. It reads the owner's last
    words from `transcript_path`. It asks whether the `You want:` line matches them,
    whether each option serves that goal, and whether a better option is missing.
- The agent hook runs inside the app, on the app's own login, on Windows and on macOS.
  The first build started a second `claude` program through `invoke_model`. That
  program's login expired on 2026-09-23 and never renews, so no check ran (measured
  2026-10-08). Owner ruling, 2026-10-08: move the check into the app. If an agent hook
  cannot do it, use a one-year token from `claude setup-token`.
- Measured 2026-10-08, with a probe agent hook on this machine: it read the last owner
  line from this session's transcript (7.4 MB) and answered in about 10 seconds.
- On a miss, the agent hook denies the call. The reason goes back to the session, which
  fixes the question before the owner sees it.

## Bounds

- A clarifying question, with no options or one option, passes first.
- Any other question with no `You want:` line, or an empty one, is denied with no model
  call.
- The owner's words are the user records with `origin.kind` "human", and the owner's
  answers in `AskUserQuestion` tool results. Task notifications, hook feedback and peer
  messages are not the owner's. The probe showed that question-box answers are tool
  results, not human records.
- A check that fails or times out lets the question through.
- After a deny, the next question in the session passes. The command hook keeps its own
  state, which expires after 30 minutes. The agent hook reads the transcript. When the
  last `AskUserQuestion` call was denied by this check, it answers ok. So a judge that is
  wrong cannot loop.
- The reason sent back to the session is capped and cleaned.
