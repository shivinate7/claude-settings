# Owner feedback goes to an inbox before the turn ends

## The ruling

When the owner opens a feedback burst, a hook writes each message to a per-session inbox. The session
must jot every message down as kinded items before a turn can end. Reason: a session acted on the first
item of a burst and lost the rest.

- **Trigger.** A message whose first word is `fb` or `fb:` opens capture mode. Every owner message
  after it is captured while capture is open. A `fb` elsewhere in a message does nothing. While capture
  is closed, no `fb ... done` form opens it. `!` is not the opener: in the Claude Code terminal a leading
  `!` runs a shell command.
- **Close.** Capture ends in four ways. The turn end does not close it.
  1. A message that starts with `fb done` or `fb: done` closes it. The rest of that message is not saved
     and not judged.
  2. A message whose last line is `fb done` (an optional colon, trailing punctuation) saves the lines
     before it and closes capture. This holds when the same message opens it. That line in a closed code
     fence or in backticks does not close. The one-line form `fb: X fb done` does not close. `fb - done`
     does not close; while capture is open, it is captured.
  3. Quiet time: 10 minutes with no captured owner message. The message after the gap is not saved
     unless it opens with `fb`.
  4. The judge. While capture is open, each message that does not open with `fb` and does not close
     capture is saved first. Then a detached child (`hooks/feedback_judge.py`) asks a Sonnet judge
     (`claude-sonnet-5-5`, through `decision_watch.invoke_model`) whether it still belongs to the burst.
     On `{"feedback": false}` the child adds the item `- fb-auto-<time> [note] -> judged not feedback`
     under that message and closes capture, only while that message is still the last one captured. An
     error, a timeout, an odd answer or a late answer changes nothing: capture stays open. The judge
     never drops a message.
- **Notices.** A message that starts with a tag in `question_outcome.MACHINE_TAGS` is agent or system
  text. It is never captured or judged. It does not close capture, and it does not reset the quiet-time
  clock.
- **Capture.** The UserPromptSubmit hook appends each captured message verbatim, with its Central time,
  to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git. Messages from other sessions
  are not captured.
- **Jot, not solve.** For each captured message, the session writes one or more items. Each item has an
  id (such as `fb-0958-2`), one kind, and a home. The work can wait. The jotting cannot.
- **Kinds and their homes.**
  - `ruling`: a decision on a question. Home: the handoff's NO HOME YET list, then a record.
  - `task`: work to do. Home: the handoff's next steps, or the repo's todo.
  - `question`: answered in the reply. Home: `answered`.
  - `note`: context with no decision. Home: `noted`.
  - `standing`: a session-only process, like a temporary CLAUDE.md. Home: the handoff's process-only
    section, which is re-read after compaction. Promote it to a ruling to keep it.
- **The gate.** A Stop check refuses to end a turn in three cases. A captured message has no items. An
  item has no kind or home. An open item id is missing from the handoff. The check reads ids, so a
  whole-file handoff rewrite that drops an item goes red. It exits on `stop_hook_active`, so it cannot
  loop.
- **Closing an item.** An item closes when its inbox line gains `[closed]`, after its work is done or
  its home holds it for good. The gate stops asking for a closed id in the handoff.
- **No silent loss.** A malformed item line is a block reason, never a crash. If capture cannot write a
  message, the hook tells the session, so it jots the message by hand. A wrong or late judge costs one
  extra saved message, never a lost one.
- **Reminder.** While capture is open, the Stop hook shows the owner one line at each turn end: send
  `fb done` to close capture, or wait 10 minutes. It uses the same open test as the capture hook
  (`local_time.is_open`), so it never says open after the quiet time. The hook prints it, so it costs no
  model tokens.
- **After compaction.** The compact hook lists open item ids and says when capture is still open.

Kind: process
Home: hooks/local_time.py
