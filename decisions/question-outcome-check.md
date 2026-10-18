# Each question passes an outcome check before the owner sees it

## The ruling

A command hook, `hooks/question_outcome.py`, runs on PreToolUse for `AskUserQuestion`. It reads the
owner's last messages from `transcript_path`. On a miss, the hook denies the call. The reason goes back
to the session, which fixes the question before the owner sees it. Reason: a prompt hook sees only the
question, never the chat, so it judges form alone (haiku-prompt-hooks).

**Format.** The standard question is a `Goal:` line first, then a `Problem:` sentence, then the options.
The `Goal:` line is a plain-words paraphrase of the goal, in the owner's terms. A paraphrase is no reason
to deny. The check reads the two rule lines for that format from `output-styles/shiv-stylisms.md` (rules
`style-question-restates-goal` and `style-question-states-problem`) at run time, and puts them in its
model prompt. So it raises no false alarm on a question that follows the style file.

**The model asks six things.** One hook asks all six, with no separate pre-check. A FLAG on any ask
denies, and the judge's reason goes to the session. A question must be plain, in every repo.

1. Does the `Goal:` line match the goal?
2. Does each option serve the goal?
3. Is an option that serves the goal better missing?
4. Can the owner answer from the box alone, with every id, code or name explained in words?
5. Does the question point at anything the box does not show? Examples: an earlier message, a time that
   refers to an earlier message, or "item 4".
6. Does each option say what the owner gains and what the owner loses, as a change for the owner and not
   for a record (rule `style-option-says-effect`)?

**The model call.** Haiku at effort `xhigh`, through `invoke_model` in `hooks/decision_watch.py`. It
starts a second `claude` program that does not share the app's login. Both hooks log in with a token from
`claude setup-token`, saved in `~/.claude/state/hook-token` on each machine and never in the repository.

**Presence and order.**

- A clarifying question, with no options or one option, passes first.
- Any other question with no `Goal:` line, no `Problem:` line, or an empty one, is denied with no model
  call. The reason names each missing label.
- A `Problem:` line before the `Goal:` line is denied with no model call. The reason says `Goal:` goes
  first.
- Only the question text counts. A `Problem:` or `Goal:` line in an option does not count.

**What the judge reads.**

- The conversation text (owner messages, assistant text, relayed cross-session messages, each labeled)
  from the owner's 3rd-last message up to the question. It reads no tool calls, tool results, task
  notices or reminders. Fewer than 3 owner messages: the span starts at the oldest found. None: the check
  did not run.
- The goal is read from owner records only: human user records, plus the owner's answers in
  `AskUserQuestion` tool results. Task notifications, hook feedback, peer messages and other tool results
  are not the owner's.
- A relay sender cannot forge an Owner block: span blocks sit between fences, and fence-like text is
  defanged.
- Over the size cap, the oldest assistant and relay text is trimmed first. Owner messages are trimmed only
  as a last resort. When the fixed text and the question alone go over the cap, the question passes and
  the hook says the check did not run.

**Fail open.**

- A model call that fails or times out lets the question through, and the hook prints one line that says
  so. That line never repeats the prompt. A question is not a destructive act, so a lost check costs less
  than a blocked question.
- Hook input that is not readable lets the question through, and the hook says the check did not run. An
  options value that is not a list counts as no options, so the question passes with no message.
- After any deny, presence or order, the next question in the session passes with no check, whatever its
  text. That clears the state. A deny state older than 30 minutes is ignored. If the hook cannot record
  or clear a deny, it does not deny, and it says the check did not run. So a wrong judge cannot loop.

Kind: process
Home: hooks/question_outcome.py
