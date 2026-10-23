# Each question passes an outcome check before the owner sees it

## The ruling

A command hook, `hooks/question_outcome.py`, runs on PreToolUse for `AskUserQuestion`. It reads the
conversation from `transcript_path`, from the owner's 3rd-last message to the question. The 3 owner messages stay whole, with no
per-message cap (owner ruling 2026-10-14 00:00 CDT). A relayed cross-session message is conversation text, labeled relayed and never
the owner's (owner ruling 2026-10-13 22:21 CDT). On a miss it denies the call. The reason goes back to the
session, which fixes the question before the owner sees it. Reason: a prompt hook sees only the question,
never the chat, so it judges form alone (haiku-prompt-hooks).

- **Format.** A `Goal:` line first, then a `Problem:` sentence, then the options. The `Goal:` line
  paraphrases the goal in the owner's terms. A paraphrase is no reason to deny. The check reads the two
  rule lines for the format from `output-styles/shiv-stylisms.md` (`style-question-restates-goal`,
  `style-question-states-problem`) at run time, so it raises no false alarm on a question that follows
  the style file.
- **One model call, six asks.** A FLAG on any ask denies, in every repo. Does the `Goal:` line match the
  goal? Does each option serve it? Is a better option missing? Can the owner answer from the box alone,
  with every id, code or name explained? Does the question point at anything the box does not show? Does
  each option say what the owner gains and loses, as a change for the owner and not for a record
  (`style-option-says-effect`)?
- **The model.** Haiku at effort `xhigh`, through `invoke_model` in `hooks/decision_watch.py`. It starts
  a second `claude` program that does not share the app's login. Both hooks log in with a token from
  `claude setup-token`, saved in `~/.claude/state/hook-token` on each machine and never in the repository.
- **Presence and order.** A clarifying question (no options or one) passes. Any other question is denied
  with no model call when it has no `Goal:` line, no `Problem:` line, an empty one, or `Problem:` before
  `Goal:`. Only the question text counts, not option text.
- **What the judge reads.** Owner messages, the assistant's text and relayed messages, each labeled by
  source. It reads no tool calls, results, task notices or reminders. The goal is read from owner records only:
  human user records and the owner's answers in `AskUserQuestion` tool results. Task notifications, hook
  feedback, peer messages and other tool results are not the owner's. A relay sender cannot forge an
  Owner block. With fewer than 3 owner messages, the span starts at the oldest one found. With none,
  the check did not run. Over the budget, the oldest assistant and relay text is cut first, then the
  oldest owner message, each cut block led by a mark and none left blank.
- **Option text.** Each option reaches the judge on one line: label, description and preview, each
  defanged and cut at 800 chars with a `[cut]` mark. The question text is defanged the same way. An options value that is not a list counts as
  no options, so the question passes with no model call and no message.
- **Fail open.** A question is not a destructive act, so a lost check costs less than a blocked question.
  A failed or timed-out model call lets the question through. So do unreadable hook input and a question
  over the size cap. The hook prints one line that says the check did not run. That line never repeats the
  prompt.
- **A wrong judge cannot loop.** After any deny, the next question in the session passes with no check. A
  deny state older than 30 minutes is ignored. If the hook cannot record or clear a deny, it does not
  deny.

Kind: process
Home: hooks/question_outcome.py
