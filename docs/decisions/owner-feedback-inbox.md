# Owner feedback goes to an inbox before the turn ends

## The ruling

A hook writes every owner message to a per-session inbox. When the owner sends a burst, the session
must jot each of its messages down as kinded items before a turn can end. No word opens or closes
capture (owner, 2026-10-26 20:57 CDT, option A). Reason: a session acted on the first item of a burst
and lost the rest, and the old `fb` and `fb done` words were easy to forget.

- **Capture.** The UserPromptSubmit hook appends each owner message verbatim, with its Central time,
  to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git.
- **Notices.** A message that starts with a tag in `shared_names.MACHINE_TAGS` is agent or system
  text. It is never captured, and it does not count toward a burst. Messages from other sessions are
  not captured.
- **Burst.** A turn's messages are the ones captured since the last Stop. They are a burst when there
  are two or more, or when one message has three or more non-blank lines or two or more bullet lines.
  Only a burst's messages need items. A lone message of one or two plain lines never triggers the guard.
  The guard keeps its turn count in `<session_id>.inbox.turns`, beside the inbox. A missing or damaged
  count makes every saved message this turn's, so it fails toward asking.
- **Jot, not solve.** For each burst message, the session writes one or more items: an id, one kind,
  and a home. The work can wait. The jotting cannot.
- **Kinds and homes.** `ruling` (a decision on a question): a decision record or a rule. `task`: the
  repo's todo or debt store. Each of the two names its file path first. The handoff and memory hold only
  in-flight notes, so they are never the home of a ruling or a task (owner, 2026-10-26, "re-point it").
  The homes come from `lint/layout.json` and the repo's extras file: layout keys `decisions`, `rules`,
  `claude-md`, `agents-md` for a ruling, and `todo` (a repo's extras key), `debts`, `debt-notes` for a
  task. `question` (answered in the reply): `answered`. `note` (context with no decision): `noted`.
  `standing` (a session-only process): the handoff's process-only section, re-read after compaction.
  Promote it to a ruling to keep it.
- **The guard.** A Stop check refuses to end a turn in four cases. A burst's message has no items. An
  item has no kind or home. A ruling or task, open or closed, names a home that is not a file under its
  kind's layout paths that some branch's tree holds. An open standing item id is missing from the
  handoff. It reads ids, so a whole-file handoff rewrite that drops a standing item goes red. It exits on
  `stop_hook_active`, so it cannot loop, but it still counts that turn's messages. When the session's
  folder is in no git repo, or the layout cannot be read, it checks no ruling or task home and says so
  in one line.
- **Answers.** `answer` (the message answers waiting-page item n): the home is `page:<n>`. The guard
  checks each open one, in every block that holds one, burst or not. A `[closed]` one is never checked.
  It blocks until the transcript shows a send after the owner's message. The send is a send_message or
  SendMessage naming n, or an ArtifactData write (set, update or batch) whose input has `n` equal to the
  item number in collection `items` (rule `questions-go-to-owner`). The k-th block with text T anchors to
  the k-th owner record with text T. A missing transcript, or one with no owner record for the block,
  passes with a systemMessage. Cost: one whole transcript read per Stop, only while an open answer item
  exists. It writes no file and starts no process. Risk kind: named incident. On 2026-10-30, item 98 was
  answered in a coordinator's chat at 15:41 and never sent to the page writer, who asked again at 16:07.
  Landed 2026-10-30. Known gap: a session that never writes the `[answer]` item is not caught. The guard
  cannot know which owner messages answer a page item.
- **Closing an item.** An item closes when its inbox line gains `[closed]`, after its work is done or its
  home holds it for good. The guard stops asking for a closed standing id in the handoff.
- **No silent loss.** A malformed item line is a block reason, never a crash. If capture cannot write a
  message, the hook tells the session, so it jots the message by hand.
- **Compaction.** The compact hook lists open item ids.

Kind: process
Home: hooks/local_time.py
