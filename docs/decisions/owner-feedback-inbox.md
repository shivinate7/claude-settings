# Owner feedback goes to an inbox before the turn ends

## The ruling

A hook writes every owner message to a per-session inbox. When the owner sends a burst, the session
must jot each of its messages down as kinded items before a turn can end. No word opens or closes
capture (owner, 2026-10-26 20:57 CDT: option A first, option C later). Reason: a session acted on the first item of a burst
and lost the rest, and the old `fb` and `fb done` words were easy to forget.

- **Capture.** The UserPromptSubmit hook appends each owner message verbatim, with its Central time,
  to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git. A note typed on a
  waiting-page card is captured the same way (that ruling's option C). A PostToolUse
  hook on `ArtifactData` (`local_time.py --page-note`) acts on a `get` of `answers` only: the routing
  session's re-read of `answers/<id>`, so an undone or withdrawn answer is never saved. Each answer
  whose `data.note` is non-empty and not `accepted pick` is appended as one block, stamped with the
  answer's `at` in Central, with the one-line text `Waiting page note, item <n> (<item>): <note>`.
  The label leaves out a missing n or item.
  The label adds no line, so a lone note is no burst. The file `<session_id>.inbox.pagenotes` holds
  one key `<url>|<doc_id>|<at>` per saved note, and a repeat read saves nothing. Cost: one process
  start per `ArtifactData` call. Files are written only when a read of `answers` returns a new note:
  the inbox and the key file. A failed save tells the session to jot the note by hand.
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
- **Closing an item.** An item closes when its inbox line gains `[closed]`, after its work is done or its
  home holds it for good. The guard stops asking for a closed standing id in the handoff.
- **No silent loss.** A malformed item line is a block reason, never a crash. If capture cannot write a
  message, the hook tells the session, so it jots the message by hand.
- **Compaction.** The compact hook lists open item ids.

Kind: process
Home: hooks/local_time.py
