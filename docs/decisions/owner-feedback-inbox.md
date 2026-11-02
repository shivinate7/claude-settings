# Owner feedback goes to an inbox before the turn ends

## The ruling

A hook writes every owner message to a per-session inbox. When the owner sends a burst, the session
must jot each of its messages down as kinded items before a turn can end. No word opens or closes
capture (owner, 2026-10-26 20:57 CDT). Reason: a session acted on the first item of a burst
and lost the rest, and the old `fb` and `fb done` words were easy to forget.

- **Capture.** The UserPromptSubmit hook appends each owner message verbatim, with its Central time,
  to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git. A note typed on a
  waiting-page card is captured the same way. A PostToolUse
  hook on `ArtifactData` (`local_time.py --page-note`) acts on a `get` of `answers` only: the routing
  session's re-read of `answers/<id>`, so an undone or withdrawn answer is never saved. Each answer
  whose `data.note` is non-empty and not `accepted pick` is appended as one block, stamped with the
  answer's `at` in Central, with the one-line text `Waiting page note, item <n> (<item>): <note>`.
  The label leaves out a missing n or item.
  The label adds no line, so a note is a burst by the Burst bullet's own test. The file `<session_id>.inbox.pagenotes` holds
  one key `<url>|<doc_id>|<at>` per saved note, and a repeat read saves nothing. Cost: one process
  start per `ArtifactData` call. Files are written only when a read of `answers` returns a new note:
  the inbox and the key file. A failed save tells the session to jot the note by hand.
- **Notices.** A message that starts with a tag in `shared_names.MACHINE_TAGS` is agent or system
  text. It is never captured, and it does not count toward a burst. Hand-backs and the
  `<cross-session-message` frame are skipped. That skip is a bandaid (owner ruling 2026-11-01
  04:29 CST, covering this skip only; debt `inbox-saves-other-notices`, which tracks other notices
  the inbox saves). Other peer messages are skipped only where a tag marks them.
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
  task. `question` (answered in the reply): `answered`. `note` (context with no decision): `noted`, or
  `not-a-grant` when the message holds a grant word that is no grant. `standing` (a session-only process):
  the handoff's process-only section, re-read after compaction. Promote it to a ruling to keep it.
  A message with a grant word (approval, approve, approved, grant, granted, authorize, authorized,
  go ahead, "permission to", "permissions to"; whole words, any case) needs one of three homes: a
  `ruling` item whose home passes, an open `page` item with its send, or a `note` item `-> not-a-grant`.
  A grant's ruling home may also be `settings.json` or `.claude/CLAUDE.md` at the repo root, if some
  branch tracks it. A plain ruling there still blocks. A lone short message counts. Risk kind: named
  incident. F47 (an all-repos grant left in chat) and F31 (a grant homed to the handoff), in the
  owner-feedback audit (claude-settings draft PR #1008, `docs/plans/owner-feedback-audit.md`). Landed
  2026-11-02. Cost: one regex on text in memory.
- **The guard.** A Stop check refuses to end a turn in four base cases, and in the Pages, grant and
  closed-note cases below. A burst's message has no items. An
  item has no kind or home. A ruling or task, open or closed, names a home that is not a file under its
  kind's layout paths that some branch's tree holds. An open standing item id is missing from the
  handoff. It reads ids, so a whole-file handoff rewrite that drops a standing item goes red. A message
  with no items is reported with the inbox file's path, its heading line and line number, and an
  example item, then each kind's home (`ruling -> <homes>; task -> <homes>; question -> answered; note -> noted;
  standing -> handoff; page -> page:<n>`, with the closed-note and grant homes in the note's text). Items added in any later turn count, so the session needs no new heading. A home outside
  its kind's paths is reported as not a tracked home of that kind, with the homes listed. It exits on
  `stop_hook_active`, so it cannot loop, but it still counts that turn's messages. When the session's
  folder is in no git repo, or the layout cannot be read, it checks no ruling or task home and says so
  in one line.
- **Pages.** `page` (the owner's ruling answers waiting-page item n): the home is `page:<n>`. The guard
  checks each open one, in every block that holds one, burst or not. A `[closed]` one is never checked.
  It blocks until the transcript shows a send after the owner's message. The send is a send_message or
  SendMessage naming n, or an ArtifactData write (set, update or batch) whose input has `n` equal to the
  item number in collection `items` (rule `questions-go-to-owner`). The k-th block with text T anchors to
  the k-th owner record with text T. An owner record is a user record, or a queued message (an owner
  message typed while the session runs, a `queued_command` attachment). A peer's words and machine
  notices are never owner records. A missing transcript passes every block with a systemMessage. A block
  with no owner record for its text passes alone, with a systemMessage. Cost: one whole transcript read
  per Stop, only while an open page item exists. It writes no file and starts no process. Risk kind:
  named incident. On 2026-10-30, item 98 was answered in a coordinator's chat at 15:41 and never sent to
  the page writer, who asked again at 16:07. Landed 2026-10-30.
  A chat pick needs the same proof. An owner block whose whole text is page picks (`<n> <letter>`, an
  optional parenthetical, comma-separated, as in `137 a, 138 b (done)`), in a repo with a waiting page
  (layout `waiting_page`), needs a send for each n, with or without a `page` item. An n that an open
  `page` item of the block names is left to that item. Prose that holds a number is no pick. Risk kind:
  named incident. F46 (the answer "143 b" never reached the page writer) and F43 ("99 a (done)", the same
  shape), same audit. Landed 2026-11-02. Cost: the transcript is read only for a pick block in a repo with
  a waiting page, or for an open page item; no file, no process (a case proves it). Known gap: a pick
  answered in a block that also holds a non-page item is not checked. A prose answer to a page item that
  names no pick is not caught either: the guard cannot know which prose answers a page item.
- **Closing an item.** An item closes when its inbox line gains `[closed]`, after its work is done or its
  home holds it for good. The guard stops asking for a closed standing id in the handoff. A closed note
  needs a home: a file some branch tracks, `step:<slug>` (the file `roadmap/data/steps/<slug>.json` on
  some branch, read by `ruling_home.value_resolves`), `page:<n>`, or `not-a-grant`. `noted` is no home
  for a closed note. A closed question homed to `answered` is never checked. Risk kind: likely risk. F88
  (a closed item with no step, record or answer behind it) is the related incident, not a measured one.
  Landed 2026-11-02. Cost: one git read per closed note, inside the Stop process.
- **No silent loss.** A malformed item line is a block reason, never a crash. If capture cannot write a
  message, the hook tells the session, so it jots the message by hand.
- **Compaction.** The compact hook lists open item ids.

Kind: process
Home: hooks/local_time.py
