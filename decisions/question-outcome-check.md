# Each question passes an outcome check before the owner sees it

## The problem

The owner often answers a question with options by asking: "Are these options aimed at
the outcome, or do they miss the point?" The next question then has the right options.
The trial `AskUserQuestion` prompt hook (decision haiku-prompt-hooks) cannot catch this. A
prompt hook sees only the question, never the chat, so it judges form alone.

## The ruling

Owner ruling, 2026-10-13 19:48 CDT: the standard question format is a `Goal:` line first,
then a `Problem:` sentence, then the options. The check reads the two rule lines for that
format from its home, `output-styles/shiv-stylisms.md` (rules `style-question-restates-goal`
and `style-question-states-problem`), at run time, and puts them in its model prompt.
So it raises no false alarm on a question that follows the style file. A question with
no `Problem:` line is denied by the presence check, with no model call, and the reason
names `Problem:` (owner ruling, 2026-10-13 14:12 CDT, "Block it too"). A question whose
`Problem:` line comes before its `Goal:` line is denied the same way, and the reason says
`Goal:` goes first. A `Goal:` line is a plain-words paraphrase of the goal, and a
paraphrase is no reason to deny. Incident, 2026-10-13 12:09: the check refused a correct
question because its goal line was not in the owner's exact words.

Owner rulings, 2026-10-08:
- Each question opens with one line, `Goal: <the goal>`, in the owner's terms. The
  owner sees at a glance whether the goal was read right.
- A command hook, `hooks/question_outcome.py`, runs on PreToolUse for `AskUserQuestion`.
  It reads the owner's last messages from `transcript_path`. It asks a model whether the
  `Goal:` line matches those messages. It asks six things in all:
  1. Does the `Goal:` line match the goal?
  2. Does each option serve the goal?
  3. Is an option that serves the goal better missing?
  4. Can the owner answer from the box alone, with every id, code or name explained in words?
  5. Does the question point at anything the box does not show? Examples: an earlier
     message, a time that refers to an earlier message, or "item 4".
  6. Does each option say what the owner gains and what the owner loses, as a change for
     the owner and not for a record (rule `style-option-says-effect`)?
- Owner ruling, 2026-10-14: a question must be plain, in every repo. The model judge asks all
  six, in this one hook, with no separate pre-check. A FLAG on any ask denies, and the judge's
  reason goes to the session. Incidents, 2026-10-14: three questions passed and the owner could
  not use them. Two named ids, a branch, a sha and a key with no words, and one pointed at
  messages the box does not hold. The third offered a false choice.
  It left out the better option.
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
- Any other question with no `Goal:` line, no `Problem:` line, or an empty one, is denied
  with no model call. The reason names each missing label. The presence check needs the
  plain label: exact case, ASCII colon, no bold, no NBSP, at a line start.
- A `Problem:` line before the `Goal:` line is denied with no model call. The reason says
  `Goal:` goes first. The order check reads both labels loosely: any one-line non-word
  prefix (space, NBSP, `>`, `-`, `#`, `*`, `_`), `*` or `_` before the colon, any case, and
  a full-width colon (`：`).
- Only the question text counts. A `Problem:` or `Goal:` line in an option (its label,
  preview or description) does not count.
- Owner ruling, 2026-10-13: the judge reads the conversation text (owner messages, assistant
  text, relayed cross-session messages, each labeled) from the owner's 3rd-last message up to
  the question. It searches back up to 16 MiB. It reads no tool calls, tool results, task
  notices or reminders. Oldest assistant and relay text is cut to SPAN_BUDGET (20,000 chars); the owner messages stay whole. Fewer than
  3 owner messages: the span starts at the oldest found. None: the check did not run.
  The goal is read from owner records only. The owner's words are user records with `origin.kind` "human", plus the owner's answers
  in `AskUserQuestion` tool results. Task notifications, hook feedback, peer messages and
  other tool results are not the owner's. Incident, 2026-10-09: the first live check read
  only typed messages, judged a question against an older topic, and denied it.
- A model call that fails or times out lets the question through, and the hook prints
  one line that says so. That line never repeats the prompt. A question is not a
  destructive act, so a lost check costs less than a blocked question.
- After any deny, presence or order, the next question in the session passes with no
  check, whatever its text (owner ruling, 2026-10-13 20:12 CDT, "Keep the free pass"; test
  O7). That clears the state. A deny state older than 30 minutes is ignored. If the
  hook cannot record or clear a deny, it does not deny, and it says the check did not run.
  So a judge that is wrong cannot loop.
- Each span block sits between `<<<BEGIN label>>>` and `<<<END>>>` fences. In the text and
  in the label, each run of 3 or more `<` before `BEGIN` or `END` becomes `<<`. A label also
  loses its line breaks, and each run of 3 or more `>` becomes `>>`. So a relay sender cannot
  forge an Owner block through the text or through its session name.
- The prompt goes to the model on stdin, so no command-line cap applies. The whole prompt stays
  within PROMPT_MAX (150,000 chars). The bound fits well inside the model's context and limits cost
  and latency; it is unmeasured against the model timeout
  (owner ruling, 2026-10-14 00:00 CDT: owner messages whole, no per-message cut). Above it, the
  oldest span text is trimmed first; owner messages are trimmed only as a last resort, from the
  oldest one. A cut owner message keeps its end, led by the cut mark; no block is left empty.
  When the fixed text and the question alone go over PROMPT_MAX, the question passes and the
  hook says the check did not run. Debt: model-clip-unmeasured.
- The reason sent back to the session is capped and cleaned.

## Limits

- `_style_rules` walks up from a rule's anchor to a line that starts with "- ", then cuts
  the first 2 characters off that text. A style file with no such line above an anchor
  would lose 2 characters from that rule. Not reachable today: both rule bullets start
  with "- ".

## Holes, named

Debts: `question-goal-line-masks-order` (a decorated Goal line masks a late Problem line), `question-problem-line-forms` (`1. Problem:` and `Problem :` do not count), `question-text-not-defanged` (question text and option labels reach the judge with no fence, and `<<< END>>>` forms pass), `judge-cut-mark-reserve-over` (the cut-mark reserve can push the prompt past PROMPT_MAX), `model-clip-unmeasured` (PROMPT_MAX fits the model context, unmeasured for token-dense text). `question-preface-punctuation` (a punctuation-led preface line before Goal is denied, and the free pass then lets the retry through).

Kind: process
Home: hooks/question_outcome.py
