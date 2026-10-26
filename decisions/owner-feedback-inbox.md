# Owner feedback goes to an inbox before the turn ends

## The ruling

When the owner opens a feedback burst, a hook writes each message to a per-session inbox. The session
must jot every message down as kinded items before a turn can end. Reason: a session acted on the first
item of a burst and lost the rest.

- **Open.** A message whose first word is `fb` or `fb:` opens capture. Every owner message after it is
  captured while capture is open. `!` is not the opener: in the Claude Code terminal a leading `!` runs a
  shell command.
- **Close.** The turn end does not close capture. A message that starts with `fb done` closes it, and the
  rest of that message is not saved. A message whose last line is `fb done` saves the lines before it and
  closes capture. Ten minutes with no captured owner message closes it. So does the judge.
- **Judge.** Each message that does not open with `fb` and does not close capture is saved first. Then a
  detached child (`hooks/feedback_judge.py`) asks a Sonnet judge (`claude-sonnet-5-5`, through
  `decision_watch.invoke_model`) whether it still belongs to the burst. On `{"feedback": false}` the child
  adds a note item "judged not feedback" under that message and closes capture, only while that message
  is still the last one captured. An error, a timeout, an odd answer or a late answer changes nothing.
  The judge never drops a message.
- **Notices.** A message that starts with a tag in `shared_names.MACHINE_TAGS` is agent or system
  text. It is never captured or judged. It does not close capture, and it does not reset the quiet-time
  clock. Messages from other sessions are not captured.
- **Capture.** The UserPromptSubmit hook appends each captured message verbatim, with its Central time,
  to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git.
- **Jot, not solve.** For each captured message, the session writes one or more items: an id, one kind,
  and a home. The work can wait. The jotting cannot.
- **Kinds and homes.** `ruling` (a decision on a question): a decision record or a rule. `task`: the
  repo's todo or debt store. Each of the two names its file path first. The handoff and memory hold only
  in-flight notes, so they are never the home of a ruling or a task (owner, 2026-10-26, "re-point it").
  The homes come from `lint/layout.json` and the repo's extras file: layout keys `decisions`, `rules`,
  `claude-md`, `agents-md` for a ruling, and `todo` (a repo's extras key), `debts`, `debt-notes` for a
  task. `question` (answered in the reply): `answered`. `note` (context with no decision): `noted`.
  `standing` (a session-only process): the handoff's process-only section, re-read after compaction.
  Promote it to a ruling to keep it.
- **The gate.** A Stop check refuses to end a turn in four cases. A captured message has no items. An
  item has no kind or home. A ruling or task, open or closed, names a home that is not a file under its
  kind's layout paths that some branch's tree holds. An open standing item id is missing from the
  handoff. It reads ids, so a whole-file handoff rewrite that drops a standing item goes red. It exits on
  `stop_hook_active`, so it cannot loop. When the session's folder is in no git repo, or the layout cannot
  be read, it checks no ruling or task home and says so in one line.
- **Closing an item.** An item closes when its inbox line gains `[closed]`, after its work is done or its
  home holds it for good. The gate stops asking for a closed standing id in the handoff.
- **No silent loss.** A malformed item line is a block reason, never a crash. If capture cannot write a
  message, the hook tells the session, so it jots the message by hand. A wrong or late judge costs one
  extra saved message, never a lost one.
- **Reminder and compaction.** While capture is open, the Stop hook shows the owner one line at each turn
  end: send `fb done`, or wait 10 minutes. It uses the same open test as the capture hook
  (`local_time.is_open`). The compact hook lists open item ids and says when capture is still open.

Kind: process
Home: hooks/local_time.py
