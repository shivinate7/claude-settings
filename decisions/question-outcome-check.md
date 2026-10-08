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
- The model call reuses `invoke_model` from `hooks/decision_watch.py`, the proven way to
  call a model from a hook on this machine. The model is Haiku at effort `xhigh`.
- On a miss, the hook denies the call. The reason goes back to the session, which fixes
  the question before the owner sees it.

## Bounds

- A question with no `You want:` line is denied with no model call.
- A clarifying question with no real options passes.
- A model call that fails or times out lets the question through, and the hook prints
  one line that says so. A question is not a destructive act, so a lost check costs less
  than a blocked question.
- One deny per question. The next try of the same question passes, so a judge that is
  wrong cannot loop.
- Agent hooks (`type: agent`) were not chosen. The docs call them experimental, and they
  do not promise that an agent hook can read the chat.
