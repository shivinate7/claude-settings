# Each question passes an outcome check before the owner sees it

## The ruling

A prompt hook sees only the question, never the chat, so it judges form alone
(haiku-prompt-hooks). A command hook, `hooks/question_outcome.py`, runs on PreToolUse for
`AskUserQuestion`. It reads the owner's last messages from `transcript_path`. On a miss, the hook denies
the call. The reason goes back to the session, which fixes the question before the owner sees it.

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

**The model call.** It reuses `invoke_model` from `hooks/decision_watch.py`. The model is Haiku at effort
`xhigh`. `invoke_model` starts a second `claude` program that does not share the app's login. Both hooks
log in with a one-year token from `claude setup-token`, saved in `~/.claude/state/hook-token` on each
machine. `invoke_model` reads that file and passes the token as `CLAUDE_CODE_OAUTH_TOKEN`. The file works
the same on Windows and macOS, needs no app restart, and is never in the repository. With no token file,
the call keeps its old path. The file may be UTF-8 (with or without a BOM) or UTF-16. Accepted risk: the
guard blocks writes to `~/.claude/state`, but not reads, so a session can print the token into its
transcript. `.credentials.json` carries the same risk. An in-app agent hook was set aside: it cannot run
`git`, which `decision_watch` needs, and in `auto` permission mode it could not open the transcript.

**Presence and order.**

- A clarifying question, with no options or one option, passes first.
- Any other question with no `Goal:` line, no `Problem:` line, or an empty one, is denied with no model
  call. The reason names each missing label. The presence check needs the plain label: exact case, ASCII
  colon, no bold, no NBSP, at a line start.
- A `Problem:` line before the `Goal:` line is denied with no model call. The reason says `Goal:` goes
  first. The order check reads both labels loosely: any one-line non-word prefix (space, NBSP, `>`, `-`,
  `#`, `*`, `_`), `*` or `_` before the colon, any case, and a full-width colon (`：`).
- Only the question text counts. A `Problem:` or `Goal:` line in an option does not count.

**What the judge reads.**

- The conversation text (owner messages, assistant text, relayed cross-session messages, each labeled)
  from the owner's 3rd-last message up to the question. It searches back up to 16 MiB. It reads no tool
  calls, tool results, task notices or reminders. Fewer than 3 owner messages: the span starts at the
  oldest found. None: the check did not run.
- Oldest assistant and relay text is cut to SPAN_BUDGET (20,000 chars). Owner messages stay whole.
- The goal is read from owner records only: user records with `origin.kind` "human", plus the owner's
  answers in `AskUserQuestion` tool results. Task notifications, hook feedback, peer messages and other
  tool results are not the owner's.
- Each option is read on one line: its label, description and preview. Each part is defanged and cut to
  800 chars (OPTION_PART_CAP). A cut part ends in `[cut]` (OPTION_CUT), and the prompt says that mark is
  a cut for length, not a missing part. The question text is defanged too.
- Each span block sits between `<<<BEGIN label>>>` and `<<<END>>>` fences. In the text and in the label,
  each run of 3 or more `<` before `BEGIN` or `END` becomes `<<`. A label also loses its line breaks, and
  each run of 3 or more `>` becomes `>>`. So a relay sender cannot forge an Owner block.
- The prompt goes to the model on stdin, so no command-line cap applies. The whole prompt stays within
  PROMPT_MAX (150,000 chars). Above it, the oldest span text is trimmed first. Owner messages are trimmed
  only as a last resort, from the oldest one. A cut owner message keeps its end, led by the cut mark; no
  block is left empty. When the fixed text and the question alone go over PROMPT_MAX, the question passes
  and the hook says the check did not run.
- The reason sent back to the session is capped and cleaned.

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

## Limits

`_style_rules` walks up from a rule's anchor to a line that starts with "- ", then cuts the first 2
characters off that text. A style file with no such line above an anchor would lose 2 characters from
that rule. Not reachable today: both rule bullets start with "- ".

