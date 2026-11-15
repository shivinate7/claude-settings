# Owner feedback goes to an inbox before the turn ends

## The ruling

A hook writes every owner message to a per-session inbox. When the owner sends a burst, the session
must jot each of its messages down as kinded items before a turn can end. No word opens or closes
capture (owner, 2026-10-26 20:57 CDT). Reason: a session acted on the first item of a burst
and lost the rest, and the old `fb` and `fb done` words were easy to forget.

Each repo has one feedback inbox that every session writes to (owner, 2026-11-01 17:44 CST).
Feedback given in any session reaches the repo it is about, not only the session's own inbox.
The repo's inbox is its triage session (project-ops operating model, Filing). There is no new
store: cloud sessions share no `~/.claude`, so a file under it would not reach them.

Triage's outbox is a separate store: `roadmap/outbox/` on the record branch (skill `project-ops`). Whether it stays the place for rulings is open. See decision `outbox-ruling-home-check`.

- **Capture.** The UserPromptSubmit hook appends each owner message verbatim, with its Central time,
  to `~/.claude/handoffs/<session_id>.inbox.md`. The file is outside git. A note typed on a
  waiting-page card is captured the same way. A PostToolUse
  hook on `ArtifactData` (`local_time.py --page-note`) acts on a `get` of `answers` only: the routing
  session's re-read of `answers/<id>`, so an undone or withdrawn answer is never saved.
  Each answer is appended as one block when its `data.note` is non-empty, not `accepted pick`,
  and not a parked-line act (`parked: true`, whose note is the entry's own text).
  The block is stamped with the answer's `at` in Central, with the one-line text `Waiting page note, item <n> (<item>): <note>`.
  The label leaves out a missing n or item.
  The label adds no line, so a note is a burst by the Burst bullet's own test. The file `<session_id>.inbox.pagenotes` holds
  one key `<url>|<doc_id>|<at>` per saved note, and a repeat read saves nothing. Cost: one process
  start per `ArtifactData` call (unmeasured). Files are written only when a read of `answers` returns a new note:
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
  task. A task may instead name `step:<slug>`, when a branch holds roadmap/data/steps/<slug>.json; a ruling
  never does. `question` (answered in the reply): `answered`. `note` (context with no decision): `noted`, or
  `not-a-grant` when the message holds a grant word that is no grant. `standing` (a session-only process):
  the handoff's process-only section, re-read after compaction. Promote it to a ruling to keep it.
  `repo` (feedback about another repo): home `repo:<owner>/<name>`. The session sends the owner's
  message, with its items, to that repo's triage session (tags `cs-build:triage` and
  `cs-repo:<owner>/<name>`). Triage always writes the page. In a run with one lane, the lane wears
  triage's hat (owner, 2026-11-10 14:32 CST, G9, triage always writes the page; 14:33 CST, G10, roles are hats). Feedback about the
  session's own repo keeps the ruling and task homes.
  The page writer rewrites each waiting-page comment wake in claude-settings into the shared template, and never answers it in a thread (owner, 2026-11-10 09:13 CST: every page feedback goes into the shared template mechanically; ruling c164: rewrite the item, never a thread reply). The wake's inbox block needs a `task` item with home `step:<slug>` (a step whose file on the record branch names the template) or a `note` item with home `not-page-form`; the Stop guard's page-form rule (`page-form-to-template`) checks it.
  A message with a grant word (approval, approve, approved, grant, granted, authorize, authorized,
  authorised, go ahead, go-ahead, "permission to", "permissions to"; whole words, any case) and an act
  or scope word (merge, push, delete, deploy, release, publish, always, standing, "from now on", and
  all, any or every right before repo, repos, PR, PRs, branch or branches), fenced text left out, needs one of four
  homes: a `ruling` item whose home passes, an open `page` item with its send, a `note` item `-> not-a-grant`, or an
  open `note` item `-> once:<act>` for a one-shot approval. A once: home is barred when the message holds a standing
  word (the guard's STANDING list, such as "whenever", "going forward", "each time", "until withdrawn", "any open").
  A grant's ruling home may also be `settings.json` or `.claude/CLAUDE.md` at the repo root, if some
  branch tracks it. A plain ruling there still blocks. A lone short message counts. Risk kind: named
  incident. F47 (an all-repos grant left in chat) and F31 (a grant homed to the handoff), in the
  owner-feedback audit (claude-settings draft PR #1008, `docs/plans/owner-feedback-audit.md`). Landed
  2026-11-02. Cost: two regexes on text in memory.
- **The guard.** A Stop check refuses to end a turn in four base cases, and in the Pages, grant and
  closed-note cases below. A burst's message has no items. An
  item has no kind or home. A ruling or task, open or closed, names a home that is not a file under its
  kind's layout paths that some branch's tree holds. An open standing item id is missing from the
  handoff. It reads ids, so a whole-file handoff rewrite that drops a standing item goes red. A message
  with no items is reported with the inbox file's path, its heading line and line number, and an
  example item, then each kind's home (`ruling -> <homes>; task -> <homes>; question -> answered; note -> noted;
  standing -> handoff; page -> page:<n>; repo -> repo:<owner>/<name>`, with the closed-note and grant homes in the note's text). Items added in any later turn count, so the session needs no new heading. A home outside
  its kind's paths is reported as not a tracked home of that kind, with the homes listed. It blocks
  nothing on `stop_hook_active`, so it cannot loop, but it still counts that turn's messages and
  judges repeats (the Repeats bullet). When the session's
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
  per Stop, only while an open page item exists (unmeasured). It writes no file and starts no process. Risk kind:
  named incident. On 2026-10-30, item 98 was answered in a coordinator's chat at 15:41 and never sent to
  the page writer, who asked again at 16:07. Landed 2026-10-30.
  A chat answer to a page item needs the same proof. An owner block whose whole text is such answers
  (`<n> <letter>`, letters a to h, as `143 b`, `143b`, `143: b` or `143 b.`; an optional parenthetical;
  answers separated by commas or lines, as in `137 a, 138 b (done)`), in a repo with a waiting page
  (layout `waiting_page`), needs a send for each n. Only an n that an open `page` item of the block names
  is left to that item. No other item line stands in for the send. Prose that holds a number is no
  answer, and `1 y, 2 n` is none. Risk kind: named incident. F46 (the answer "143 b" never reached the
  page writer) and F43 ("99 a (done)", the same shape), same audit. Landed 2026-11-02. Cost: for each
  such block, one `git rev-parse` and one transcript read, inside the Stop process (unmeasured). The transcript is
  read only for such a block in a repo with a waiting page, or for an open page item. No file written (a
  case proves it). Known gap: an answer
  to a page item inside a longer message, or in prose, is not caught: the guard cannot know which prose
  answers a page item.
- **Repos.** `repo` items (feedback about another repo): the home is `repo:<owner>/<name>`. The guard
  checks each open one, in every block that holds one, burst or not. A `[closed]` one is never checked.
  It blocks until the transcript shows, after the owner's message, a send_message or SendMessage whose
  text names `<owner>/<name>` as a whole token. Letter case is ignored; a trailing period or URL path
  still counts. The home is read as a ruling home is (`home_path`). Backticks or quotes come off only when
  both ends match. A `#anchor` drops. A trailing `:,;.` strips. Then the `<owner>/<name>` check runs. A home
  part that is not letters, digits, `.`, `_` or `-` is malformed and blocks. Same anchoring and owner-record
  rules as Pages. The stand-down systemMessage starts "Feedback guard: repo sends not checked"; the page one
  starts "Feedback guard: page sends not checked". Cost: the one transcript read Pages makes, per Stop, only while an open page or repo item
  exists (unmeasured). No file written, no process started. Risk kind: likely risk (owner-named gap, 2026-11-01).
  Landed 2026-11-01. Known gap: the guard cannot tell the send went to that repo's triage, only that it
  names the repo.
- **Page filing.** In a repo with a waiting page, an open `page` item whose send is proved also needs its
  number filed. The guard reads the waiting copy, the `items/` folder of the waiting export on
  `origin/<record branch>`, as of the last fetch. It fetches nothing. A read-back also proves the filing:
  an ArtifactData get, list or query of the waiting page's `items` collection, after the owner's message.
  Its result must return a document with `n` equal to the number. A read with `out_dir` does not count,
  because its result lists files. It blocks when neither holds the number. The remedy has two routes. Ask
  the page writer to export the waiting copy into its folder on the record branch and push it, then fetch
  that branch. Or read the item back from the page. A send the check stood down on skips this check. A copy that
  cannot be read blocks nothing; a systemMessage starts "Feedback guard: page filing not checked", and
  the send check decides alone (rulings fb-1312-1 and fb-1313-1, the owner's grant for this check; fb-1311-3,
  verify each filing on origin or by read-back). Cost: one `git rev-parse` and one `git grep` of the copy's
  items, inside the Stop process. They run once per Stop with an open page item whose send is proved and
  whose number no read-back returns (unmeasured). The read-back uses the transcript read Pages makes. No file written,
  no process left running. Risk kind: likely risk. Landed 2026-11-02. Known gap: it proves that item n exists in the copy
  or on the page, not that this answer was filed on it.
- **Repeats.** A model matches each new item's owner message, by meaning, against older feedback and
  work, so the owner's words meet the code's names ("carousel" for code that says "wheel") with no
  glossary to keep up. It runs in the Stop guard, on every Stop including `stop_hook_active`. New
  items are well-formed, open items whose ids the turn state's `judged` list lacks; a state file
  from before the key counts the items already there as judged. One call per Stop covers all of
  them, through `decision_watch.invoke_model` (`claude-haiku-5-5`, 45 s, no effort; the Stop hook's
  timeout is 60 s). Candidates are cut to 300 characters each, at most 400, roadmap first. Each
  source has its own share, so one cannot crowd out the rest: 200 roadmap steps, 100 backlog lines,
  100 inbox blocks. Within a source the share keeps the front: roadmap steps not marked done come
  first, todo and notes lines go newest (last) line first, and inbox blocks newest first. They are: steps at `refs/remotes/origin/roadmap` (one `git grep`,
  never fetched); the layout's debt, todo and notes files in the working tree; this inbox's
  blocks. They also include the blocks of the 50 newest other inboxes whose sidecar
  `<sid>.inbox.repo` holds a folder at or under the repo root. Capture writes that sidecar once per
  session, when its cwd is in a repo. It walks up for `.git` and starts no process. The model names
  at most one candidate per item. Each item has its own candidate list: the judge drops the step,
  debt, todo or notes file the item's home names (every line of a todo or notes file) and the item's own
  owner-message block, even when two blocks share a minute (ruling 2026-11-11 13:03 CST,
  restart plan R38). Another message of the same Stop, and the same text in another session's
  inbox, stay candidates. An item with no candidate left is not asked. A hit appends ` repeats <ref>`
  to the item line (one inbox rewrite through a temp file) and prints one systemMessage line. A mark
  never blocks the turn. A line that cannot be found is reported as not marked. The session merges
  the work or drops the mark. A dropped mark is not judged again. A model error or odd answer marks nothing and adds one
  systemMessage line. The items count as judged, so there is no retry loop. Cost: a Stop with no new
  item or no candidate makes no call. Otherwise it makes one call, one `git grep` and one rev-parse (unmeasured).
  It lists the handoffs folder and reads one sidecar per inbox there. It writes the turn state, and
  on a hit the inbox. Capture adds one small file per session and no process (unmeasured). Risk kind: named
  incident. On 2026-11-01 17:44 CST the owner said "carousel" in a repo whose code said "wheel", and
  nothing matched the repeat. Ruling 2026-11-01 17:57 CST: a model's meaning match, no glossary.
  Landed 2026-11-01. Known gaps: inboxes from before the sidecar are not searched. Item ids
  `fb-HHMM-n` can recur after a day, and a recurring id counts as judged, so its item is not judged. A cloud container
  starts with no old inboxes, so there the roadmap and backlog do the work. Outside a repo only this
  inbox's blocks are candidates. A session whose cwd is a linked worktree has its own top level, so
  inboxes bind per worktree, not per repo. A session's cwd is usually the primary checkout.
- **Closing an item.** An item closes when its inbox line gains `[closed]`, after its work is done or its
  home holds it for good. An item is closed by `[closed]` as a whole token after the home, with trailing
  text allowed, or by `[closed]` at the line end. The guard stops asking for a closed standing id in the
  handoff. A closed note
  needs a home: a file some branch tracks, `step:<slug>` (the file `roadmap/data/steps/<slug>.json` on
  some branch, read by `ruling_home.value_resolves`), `page:<n>`, or `not-a-grant`. `noted` and
  `process-only` are no home for a closed note. A closed question homed to `answered` is never checked. Risk kind: likely risk. F88
  (a closed item with no step, record or answer behind it) is the related incident, not a measured one.
  Landed 2026-11-02. Cost: for each closed note homed to a file or a step, `git rev-parse`, `git for-each-ref` and
  `git cat-file`, inside the Stop process. No file written. When the folder is in no repo, the check
  passes and a systemMessage names the closed note homes.
- **No silent loss.** A malformed item line is a block reason, never a crash. If capture cannot write a
  message, the hook tells the session, so it jots the message by hand.
- **Compaction.** The compact hook lists open item ids.

Kind: process
Home: hooks/local_time.py
