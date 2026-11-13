---
name: waiting-page
description: Use when a session has a question, a decision or a task for the owner, when it starts a turn with items open on the waiting page or parked lines on it (the page's writer), or when a repo makes its waiting page. Puts every item waiting on the owner on one page per repo, and reads the owner's answers back.
---

The waiting page is the one private page per repo or project. Its Questions tab holds every item
that waits on the owner. Its Status tab shows the repo's roadmap, read only. Only triage writes an item (owner, 2026-11-10 14:30-14:32 CST). A lane that wears triage's hat in a run with one lane writes as triage (owner, 2026-11-10 14:33 CST).

In a larger build the owner talks in two places: the page for anything waiting on the owner, and the coordinator's chat for anything new, never a lane (decision `session-tiers`, the session roles; owner, 2026-11-10 16:46 CST, G15, the two-places ruling).

A lane never writes an item, unless it wears triage's hat in a run with one lane. A lane puts its
question in its report, and sends it to its parent in the same turn. Triage writes the item with the asking session as `owner`, and routes the
answer back to the lane or its next try. Not built: the route from a lane to triage.

Every repo's page is the same template. The page is fixed. All content lives in its database,
through the ArtifactData tool. Two exceptions are stored in the page itself: a design mockup (see
"Add a design") and the roadmap block (see "Update the roadmap block"). Rule `questions-go-to-owner` (questions go to the owner) sends each
question here. Decision `questions-go-to-owner` holds the rulings.

The rest of the page's rules live in sibling files under `reference/`. Read a file only when its row applies.

| Topic | File | Read it when |
|---|---|---|
| Keep the page on main's code | `reference/republish.md` | Before the page is republished, at each writer wake. |
| Rebuild a page from the repo | `reference/republish.md` | The page is gone, or moved to an org this account cannot read. |
| Merge a copy into a live page | `reference/republish.md` | Two accounts each wrote a page for one repo. |
| Keep a copy in the repo | `reference/copies-and-accounts.md` | At each writer wake, before any republish, and in a rebuild or a merge. |
| Register and cite an artifact | `reference/copies-and-accounts.md` | A repo registers an artifact, or a decision or debt cites one. |
| Before you switch Claude accounts | `reference/copies-and-accounts.md` | Before the account, the org or the machine changes. |
| Rotate the writer | `reference/routing-and-sessions.md` | The writer role moves to a new session. |
| Route an ask | `reference/routing-and-sessions.md` | An ask arrives in `asks/`. |
| Message another session | `reference/routing-and-sessions.md` | A session sends or reads a message to or from another session. |
| Make a repo's page | `reference/repo-pages.md` | `layout.py waiting-page` prints `unknown` for a repo, a fork makes its own page, or a page is rebuilt. |
| Update the roadmap block | `reference/repo-pages.md` | The roadmap block is rebuilt. |
| Update a repo's pages | `reference/repo-pages.md` | A batch changes `page.html`. Also before a write that sets a ruling, `reply`, `replied`, `lastAnswer`, `lane`, `waits`, `multi` or `ranked`, and when a design is republished. |
| Add a design | `reference/designs.md` | An option needs a mockup picture. |

## Find the page

Run `python3 ~/.claude/lint/layout.py waiting-page <repo root>`. It prints the URL, or `unknown`.
The URL is the `waiting-page` key in the repo's extras file, `.claude/layout-extras.json`.

- `unknown` is not an error. Ask in the reply while anything runs, else in the terminal question
  box, and say in one line that the repo has no waiting page.
- Never guess a URL, and never use the page of another repo.

## The database

Read every ISO time you write (`added`, `replied`, `ruled`, `read`, `filed`, `answered`) from `~/.claude/bin/now-central --iso`, never from memory.

- `items/<id>`: one per waiting item. The database key is the item's id. The `id` field is optional
  and ignored: the page, the guard and the tools read the key. Fields: `n` (a stable number the owner answers by),
  `kind` (`decision` or `task`), `status` (`open` or `closed`), `added` (ISO time), `ref` (each id
  with its plain name), `title`, `short` (optional, 24 characters or fewer: the name on the wide left list; longer or missing, the list shows `title` cut with an ellipsis), `owner` (the session that reads the answer at its wake), `home` (the step, PR or
  record the answer goes to; a step is its bare step id, so the roadmap upkeep row can match it), `context` (plain text, line breaks kept).
  - The page derives the tier from these fields. Never write a tier.
    - `holds` (one plain sentence: what is stopped until the answer) puts the item in Blocking.
    - `by` (an ISO deadline) puts an item with no `holds` in Upcoming.
    - An item with neither is in Whenever.
    - `stands: true` puts the item in the last section, Pick stands (see "Add an item").
  - `arbiter: true` marks a ruling: an item the arbiter decided (decision `session-tiers`, Arbiter, "On the page").
    The arbiter hands each ruling to the writer. The writer writes it closed, with the item's `status` `closed`,
    `home` the ruling's record id, `recommended` (old name `pick`) the ruled option's key, `why`, and `ruled` (an ISO time). It cites the ruling.
    The page shows it in "Arbiter rulings", newest first, with one Overturn button. Every other closed item with a `closed` time stays as one line in "Answered" until the owner marks it read. A closed item with no `closed` time counts as read and stays hidden.
    A ruling is never in a tier and never counts as open. It keeps `owner`, `n`, `title` and `options`:
    the card names the ruled option from `options`. Write a ruling only on a page that `stale_pages.py` reports
    current (see "Update a repo's pages"). An older page hides closed items, so the ruling would not show.
  - `rank` (an integer, lower first) orders items inside a tier. Only the page's writer sets it
    (see "The writer"). It never moves an item to another tier. An item with no `rank` follows the
    ranked items, newest first. A group sits together at its best member's `rank`. Inside a tier,
    new items come first, then seen ones, each part in that order. Seen: the item is open, has no
    `answers/<id>`, and was `added` before the owner's last Send (the newest `answers/<id>.at` or
    `lastAnswer.at` on any item, closed ones too). A group is seen only when every member is; a ruling is
    never seen. The page works this out once at load and keeps it; a reload works it out again. A seen card keeps every answer part open (options, or steps, command and links; the ready
    line; Mark done; None of these; the note box), under a divider that reads "Asked before". An item the owner
    still owes never folds. It folds only once answered (see "Answered" below).
    An item that arrives after load is new, and so is any group that gains a member after load. It sorts first in its
    tier, ahead of the other new items. A group is an arrival while any member is. The page keeps the set of ids
    present at load. An open card sits above an answered one: a Send moves the sent card out of its tier (see "Answered"),
    and a group moves only when every member is sent.
  - An item answered at or before load (`answers/<id>` exists, filed or not) sits in the
    "Answered" section, after the open tiers and before "Arbiter rulings", newest answer first. A group sits there only
    when every member is answered, as one frame headed by its group title, or "Answered together" when it has none, at its newest member's time. A group with an
    open member stays whole in its tier. The page works this out once, when the items and answers have loaded, and keeps
    it: a receipt that arrives later moves no card until a reload. The page has one switch, `SENT_MOVE`. With "sink" (the
    default) a Send moves each sent card to this section, folded, and the next open card takes its place; Undo puts it
    back in its tier, open. A group moves whole. With "stay" a sent card keeps its place until reload. The sub-head reads
    "Your sent answers, newest first." under "sink". The section is open on load, each card folded
    to its top row, title and answer line; one control holds the owner's note, last answer and reply. A card with a
    new reply (see `replied`) opens at load and carries the mark "New reply", in place. A Change keeps
    the card in the section, open, until reload, and a reply that arrives opens a card in place. A card that holds a draft, a stood pick or a pending withdraw stays open. With no answered item the page draws no section and no rail row.
  - `group` (a slug) puts the item in one frame with the other items of that group. See `groups/<slug>`.
  - `port: true` marks a question about a port or redesign of an existing app. Set `port: false` on an item
    whose text uses the word port for another meaning. Such an item needs a line in `context` that starts
    "Departs from: <file>:<symbol> — <what changes>" and never has `holds`. The writer refuses it otherwise
    (guard rule `port-question`). The existing app answers every other question: read it, never ask.
  - `widens: true` on an option marks one that widens what a shared tool accepts: a second accepted form,
    an allow-list entry or a per-repo exception. Its card shows "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo": a repo
    that differs from a shared format changes to match it. `recommended` never names such an option, and a list `recommended` never holds its key (the old name `pick` is read the same way). The writer refuses
    it (guard rule `uniform-pick`). An update that sets `recommended` carries `options` again: the guard cannot see the stored field.
  - An option may carry `links` (a list of `{label, url}`): its card shows them, and each opens in a new tab. An option that
    asks the owner to press in a web app carries a link to that exact page (for a pull request or an issue, its number in the url).
    The writer refuses it otherwise (guard rule `press-link`). An update that sets `options` carries each option's `links` again,
    and an update that sets `steps` carries `links` again: the guard cannot see the stored fields.
  - `look: true` marks a question about how something looks. Every option card with no picture then
    shows a warning. Never set it on any other question.
  - `designs` (a list of `{slug, label, file}`; the guard requires `file`) shows mockups (see "Add a design"). An option names its picture with `design` (a slug in `designs`),
    and the picture sits at the top of that option's card.
  - A decision adds `options` (a list of `{key, label, how, gain, lose}`, plus `design` on a look question, plus an optional `differs` and `widens`), `recommended` (the key you
    recommend; `pick` is its old name, and a page reads `recommended` first, then `pick`, so an old item stays readable) and `why`. `pick` is never the owner's answer: his answer is `choice` in `answers/<id>`. Each key is the letter the page shows for its position, in lowercase: `a`, `b`, `c` in order (guard rule `option-letter-keys`).
    One letter per option: an option's `label` and its mockup carry no letter of their own (no "B:", no "Option B"), since the page's key is the only letter (guard rule `option-letter-keys` refuses a label that opens with another letter's tag).
    An option keeps the letter it was shown with (owner ruling R60, decision option-keys-are-letters). Each option carries a unique short `id`, a slug that is never a lone letter, and the item carries `shown`: the options as first shown, in order, each as `{key, id, label}`. A later write keeps each shown position's key, id and label. A rule-driven change adds a `note` to the option ("Now means: ...") and reorders nothing; the page shows the note on the card. A new option goes at the end. Guard rule `option-letters-frozen` refuses an open decision's write that carries `options` in any of four cases. The write has no `shown`. An option has no unique id. There are fewer options than shown. A shown position changed in key, id or label. A first `set` carries a `shown` equal to its options; an update may append. The guard also refuses an `options` that is not a list. Known limit: the guard cannot see the stored item, so a write that rewrites `shown` itself passes. A held answer is the backstop.
    One source for the chat question and the item: `python3 skills/waiting-page/question_source.py < spec.json` (function `render`) writes the chat text (`Page item: <id>`, then `a) <label>` per option) and the item's `options` and `shown` from one spec, so the two copies cannot differ. A spec that carries the earlier `shown` and `changes` ({key: note}) keeps each changed option's key, id and label and adds the note; `render` raises when the options do not extend `shown`.
    When an option asks for a settings change, its label names `settings.json` and the entry by its exact title or key, one entry per option. Otherwise no relayed grant covers it (decision relayed-grant-read-from-page).
    Never use the key `none`. The page adds its own "None of these" option
    with that key. Name an option in every item text by its letter ("option A", "pick b"), never by another key. The page shows each option by its letter by position and names a pick by its `label`, never by its `key`. The page never preselects an option: it stars `recommended`, labelled "Recommended", and a tap on the starred option picks it.
    - `multi: true` marks a decision whose options can all be done together. The owner ticks any number of them, so the card shows checkboxes in a group, not radios.
      `ranked: true` also asks the owner to put the ticked options in order, best first. `ranked` implies `multi`. Never call it `rank`: `rank` is the writer's in-tier order.
      On such an item `recommended` is a list of option keys, in the recommended order when `ranked`. It is not empty, has no repeat, and each key is a key of `options`. The page shows and saves an unranked `recommended` in option order. `why` stays one text.
      A `recommended` that does not fit the kind of item is not shown: no star. A list `recommended` on a pick-one item is one such value.
    - `differs` is a list from `picture`, `how`, `gain`, `lose`: the parts that set this option apart from the others. The page marks each named part with a bar, a "≠" and hidden words "Sets this option apart", and adds one line under the options: "≠ marks what sets an option apart." It drops a named text part whose text equals that part in every other option, a `picture` on an option with no picture, and any other name. Name few parts, and only true ones. With no `differs`, the option shows no mark.
  - A decision carries the question form of rule `style-question-form`. The lines go in `context`, and each option has a non-empty
    `gain` and `lose`. `context` also has a line that starts "Departs from: <what on main> — <what changes>"; a change that restates main does not count. The writer refuses a decision without it (guard rules `question-form`, `owner-judge` and `question-departs`). A decision with
    `status: "closed"` needs none; decision `question-form` holds the other exemptions. An update that
    carries `kind: decision` and `context` carries the lines again, and one that carries `options` carries each `gain` and `lose` again:
    the guard cannot see the stored fields.
  - A task adds `steps` (a list of strings), `links` (a list of `{label, url}`), `command` (`{powershell, mac}`, two
    strings) and `minutes` (a number, or text such as `3 min`). `powershell` is PowerShell 5.1-safe: no `&&`, `||`,
    `<<`, `<<<`, `/dev/null` or `export`. `mac` is bash or zsh. Never mix shells in one. The item shows each in a closed disclosure with a Copy
    button that works while it is closed, PowerShell first on Windows. A stored one-string `command` shows as one block
    with no shell label. A step that presses in a web app needs a link in `links` (guard rule `press-link`).
    A step never sends the owner to a file for a command and never holds one: put it in `command` and say "paste the
    command below". The writer refuses a step with a shell line in backticks, and a `command` without both shells
    (guard rule `command-in-item`). Each shell in `command` opens with the gh login switch of rule `style-hand-off-gh-login`, before any other gh line (guard rule `gh-login-switch`). A `str_replace` on `command` that adds a gh line carries the switch in its `new_str`.
  - A task carries a line in `context` that starts "Why yours: <why only the owner can do it, and the check that showed it>".
    When the cloud refused the act, the session first asks a session on the owner's computer
    (`list_computer_folders`, then `request_computer_folder`), and the line names that outcome.
    The writer refuses a task with no such line (guard rule `task-names-check`).
    When the line says a session cannot do the act (refused, denied, cannot, unavailable, 403), it ends with a cite: `(route <id>)`, an id from the route rows file whose row says refused or asks, or `(measured <YYYY-MM-DD>, <check and result>)`. A row that says the act works, an id no row holds, a measurement with no date, and a tool name in backticks are refused (guard rule `task-why-cited`).
  - `reply` (a string) is what the session says back to a comment or a note. The card shows it as "Reply: <text>".
    A reply over 220 characters folds to three lines, with a "More of the reply" button.
  - `replied` (an ISO time) is when the writer last wrote `reply` or changed `waits`. The writer sets it to now in the same update. A write of `lastAnswer` alone never sets it, because it copies the owner's own answer. Dropping `lane` sets none. The page
    marks an item "New reply" when `replied` is later than both the owner's last Send (the same time that decides seen) and the owner's last visit
    (`waiting.visit` in the browser, which the page writes on each load; with none, the last Send alone decides). The page reads both once at load, so a Send or a
    visit on the open page moves no mark. A roadmap step is marked "Updated" the same way, when its `updatedAt` is later than the last visit; with no visit, no step is marked. An answered card with a new reply opens in place, and no card moves. Write no `replied` for any other change. While `waits` is set, `--unread` does not read `replied` as a reply to an answer, since a wait moves it too: a receipt clears the line.
  - `lastAnswer` (`{choice, note, at}` on a decision, `{done, note, at}` on a task, `{act: "park", note, at}` on an item the owner parked and then unparked) is the owner's last answer to this item.
    The card shows it above the reply, as "Your last answer, <time>". The writer copies it from `answers/<id>` before it
    deletes that record (steps 2 to 4 of "Route and close"), and from a chat answer. When the item carries `shown`,
    each shown option keeps its key, so `lastAnswer` keeps its `choice`. An item with no `shown` may have moved its keys: write `lastAnswer` again without `choice`.
  - `lane` (the receiver's branch slug, or its tier, such as `batch-runner` from its `cs-build:` tag, when it has no branch) is set when the item is posted
    with `holds` for a lane, and when an answer takes the busy-lane path. An item that holds a lane and has no `lane` routes its answer to `owner` only, so `--unread` names it `lane-missing`. The card shows "waits on lane <slug>" in its top row. The item stays open until the receiver
    reports the act done, and then the owning session closes it and deletes `answers/<id>` (see "Route and close", the busy-lane path).
  - `closed` (an ISO UTC time with a trailing `Z`) is when the item closed. The session that closes the item writes it in the same `update` as `status: "closed"`
    (step 2 of "Route and close"; the writer does the same for a chat answer). The page shows a closed item that has a `closed` time as one line in "Answered" until the owner marks it read.
    A closed item with no `closed` time counts as read, so the page never shows it.
  - `dismissed` (an ISO time, or `null`) is the owner's read mark. Only the page writes it, at the owner's press, with `update`: Mark read writes the time, and Mark unread writes `null`
    (the runtime has no field delete). No session writes `dismissed`. A session changes a closed item, or any item the owner may have marked, only with `update`, never `set`:
    `set` drops `closed` and `dismissed`, and the item then counts as read and leaves the page. A `replied` time later than `dismissed` brings the line back.
    A re-ask (an open item that is owed again) shows as a card, whatever `dismissed` says. A Mark read on an open item changes its version, so a close pinned to the version you read
    can conflict. Read the item again and retry the close. Never drop it.
  - `waits` (`{repo, run}` or `{repo, pr}`: a CI run id or a PR number) is set while the item waits on that run or PR. Setting or dropping it also sets `replied` to now. `run` and
    `pr` are a whole number above zero, or a string of digits with no leading zero; any other value reads as no wait. An item
    with `waits` and `lastAnswer` reads as answered on the page.
    `stale_pages.py --items` names each open item's wait `ended`, `waiting` or `unknown` (see "Route and close").
  - `repo` (`owner/name`, as in `waits`) is the repo the question is about. It is required on every open decision and task. A page's own repo writes its own name.
  - `checked_with` is the session id of the triage, coordinator or owner's-computer session of that repo that said the owner has not ruled on it. It is required when `repo` is not this page's repo. It is never the session in the item's `owner` or, in a cloud session, the session that writes the item. To change `repo` or `checked_with`, send an `update` that carries both; a `str_replace` on either, or an `update` with `checked_with` and no `repo`, is refused. The writer refuses an item without it (guard rule `question-checked-with-repo`).
  - Before writing `reply`, `replied`, `lastAnswer`, `lane`, `waits` or `recommended`, the writer checks that the page is current with `stale_pages.py`, the same
    check as `multi` and `ranked` (see "Update a repo's pages"). An older page draws none of the six. A page published before the `recommended` change reads only `pick`, so it shows no star for `recommended`: after the change merges, the writer republishes the page.
  - The page draws only the top-level fields that its `itemFields` block lists (`page.html`). A write that names another
    top-level field is refused (guard rule `item-field-rendered`), and a stored item that carries one shows a warning on its card.
    To add a field, draw it on the page and add its name to that block. A key inside `options` or `steps` is not judged. `shown` is in the block; an option's `id` and `note` sit inside `options`, so they are not listed.
    When the page is current, it saves `optionId` in an answer, and it draws an option's `note`. It lists `shown` in its item fields and draws nothing from it. An older page does none of these. Run `stale_pages.py` before you write `shown`, an option `note` or `optionId`.
    An update removes a stored field with `{"__delete__": true}`.
- `groups/<slug>`: `title` and `why`. `why` is one sentence on how the items of the group connect.
  Write the record in the same step that sets `group` on the second item.
- `answers/<id>`: the page writes it when the owner presses Send. Fields: `item`, `n`, `at` (ISO
  time), `note`, and `choice` (a decision) or `done: true` (a task). A task answer may instead be
  a note with no `done`. A pick that stands writes `choice` equal to `recommended`, with the note
  `accepted pick`. A tap on the starred option is an ordinary pick, with no such note. On a `multi` item `choice` is a
  list of option keys, in rank order when `ranked` and in option order otherwise. A stood pick writes the whole `recommended` list in that order. "None of these" writes
  `choice: "none"`, and the page sends it only with a note that says what the owner wants
  instead. A note typed with no option picked is the same answer: `choice: "none"` plus the note.
  On an item whose pick stands, a note with no new pick sends the stood pick plus the note.
  A decision answer also carries `label`, the words of the choice as the page showed them, so a reader sees what the letter meant: "A: Red" for a pick (the letter by position, then the option's `label`), a list of those for a `multi` item, "none of these" for none. `choice` stays the key, or the list of keys, and decides the answer. The answer also carries `optionId`, the id of the option picked (a list for a `multi` item), when every picked option has an id (ruling R60). If the item's option at that key no longer has that id, or, with no `optionId`, no longer has that letter and label, `page_grant.py` prints `held:` and exits 3: the owner confirms in words, and the answer is no grant. The same holds for a choice key the item no longer holds, when it equals `--pick`. The fields are new, so an older answer has neither.
  A changed answer that the owner leaves empty is withdrawn: Send reads "Withdraw answer" and
  deletes `answers/<id>`. The page re-reads the record first and leaves one that changed. A withdraw
  has the same 8-second Undo as a Send, and tells no session. Undo (8 seconds after a Send) deletes the
  records that Send wrote, or puts back the answer they replaced.
  A Park press on an open decision or task card writes `{item, n, at, act: "park", note}`: no `choice`, no `done`, no `parked`.
  It goes to the page's writer ("Route and close"), because only the writer writes `meta/page`.
- `answers/park.<id>`: the page writes it when the owner presses Send on a "Parked by you" line. Fields: `parked: true`,
  `id` (the entry's `id`), `act` (`unpark` or `drop`), `ref` and `note` (copies of the entry's), `at`. It names no item and
  counts toward none. Its key holds a dot, which an item id never holds, so it never meets an item's key. Undo and withdraw delete it, as for any answer.
- `receipts/<id>`: written by the owning session, never by the page. Fields: `read` (ISO time the
  session read the answer) and `filed` (ISO time it moved the answer to `home`). Write both as ISO UTC with a
  trailing `Z`: the `--unread` check reads a time with no zone in the host's zone. The page shows
  them on the answered card. In a tier (an item answered on the open page), with no record the card says
  "Answered, filing pending" and the save time; with `filed`, "Answered, filed in <home>" (the item's `home`) and the
  filed time. In the Answered section, the same two read "Filing pending, sent" and "Filed in <home>". With only
  `read`, the card also says "Read by <owner>" and the time.
- `asks/<id>`: one per ask typed in the page's Ask box, and one per reply the owner writes under an answer, never an item. The owner stacks asks with Add to list (nothing is
  written), then one Send writes every stacked ask and the typed box. The page writes `id` (the key,
  `ask-<base36 ms><2 chars>`), `text` (4000 characters or fewer, line breaks kept) and `at` (ISO time) once, at Send. A reply
  also gets `re`, the id of the answered ask it follows, written once at Send. No session writes `re`. The page writes one more
  field later, at the owner's press: `dismissed` (ISO time), on a thread's root ask only, with `update` (Mark read). Mark unread writes
  `dismissed: null` (the runtime has no field delete). It never deletes or replaces the owner's `text` or a `reply`. No session writes
  `dismissed`. A session answering a dismissed record uses `update`, which keeps it (see "Route an ask"). A reply goes through the same
  Send, Undo and wake comment as an ask. Its comment reads "Replied on the waiting page. Writer: <writer>. Ask <id> re <re id>,
  answered by <owner of the ask `re` names>: <text>." The asks
  of one Send share one `at`, and their ids rise in the order the owner typed them, so the id breaks the tie: the highest
  id is the last typed. One Undo (8 seconds) deletes every ask of that Send; it checks the 8 seconds before each delete, and a Send waits until the Undo ends. One wake comment tells of the whole Send: "N asks:
  <id>: <text>; …", or "Ask <id>: <text>" for one. A session writes only `owner` (the session that has the ask), `read` (ISO time),
  `reply` (plain text, line breaks kept), `answered` (ISO time of `reply`), `home` and `filed` (where a feedback ask
  went, in plain words, and when). Never write `text` or `at`: ArtifactData writes as the owner, so this sentence is the only
  guard. A session changes an ask only with `update`, never `set`: `set` replaces the record and drops the owner's text.
  An ask with `reply` is answered. The page lists threads newest first by the `at` of their root ask, and a reply sits in its root's thread.
  It shows each waiting ask, each new answer (whatever its age) and the newest 3 answers already seen. An answered ask whose `home` a session wrote,
  with no record in its thread waiting, is routed: the page shows it as one line, its `home` and the first sentence of its `reply`, until the owner marks it read.
  A routed ask answered before the page's `READ_FROM` time counts as read.
  A thread with a waiting reply always shows. The page hides a read thread (root `dismissed` is an ISO time) unless a
  record in it waits or has an `answered` later than `dismissed`, and opens it again under "Show N read asks". No session deletes or replaces an ask.
  An ask is never a grant: an act that needs one becomes an item.
- `meta/page`: `writer` (the one session that writes the page's items, see "The writer"),
  `checked` (what the items were measured against), `parked` (a list of
  `{id, ref, note}`: `id` is a slug of 32 characters or fewer, unique in the list, that you set; a line with no `id` has its acts off) and `identity` (`{name, mark, brand, face, icon}`). The field `woke` is optional.
  - `woke` is the ISO UTC time of the writer's previous wake, with a trailing `Z`. Only the writer writes it. At a comment wake the writer runs `--unread` ("Read the answers"), then writes `woke` at the end of that wake. With no `woke`: the first run; every answer with no receipt is listed. An answer still in its 10 s wait may be listed once. The cost is one message with no answer text.
  - `name` is the repo's name. It shows on the colour bar and in the tab title.
  - `mark` is one letter for the bar. It defaults to the first letter of `name`.
  - `brand` is one hex colour, such as `#f47820`. The page derives every colour from it and
    checks each text colour for 4.5:1 contrast. With no valid `brand`, the page keeps its neutral
    colours.
  - `face` is `sans` (the default), `serif`, `display` or `classic`. It sets the face of the name.
  - `icon` is the repo's own icon as an inline `data:image/svg+xml` or `data:image/png;base64` URI,
    at most 16384 characters (the page's `ICON_MAX`). It replaces the letter on a white or dark tile,
    whichever more of its pixels stand out on. A square icon reads best: a wide one shrinks to fit
    the 22px slot. The page never fetches a URL; any other value keeps the letter.

The page hides an item with status `closed`, except an arbiter ruling (see `arbiter` above). It shows an item as answered when
`answers/<id>` exists: a green edge and the badge "Filing pending, sent" or "Filed
in <home>" in the Answered section (see `rank` above), never "waited". An item answered on the open page goes where `SENT_MOVE` says (see "Answered" above); while it keeps its tier it
carries the badge "Answered, filing pending" or "Answered, filed in <home>". It stays on the page until the owning session closes the item.

## The writer

Each page has one writer: triage (owner, 2026-11-10 14:30-14:32 CST). In a run with one lane, the lane
wears triage's hat and writes it (owner, 2026-11-10 14:33 CST). The page's name for it is `writer` in `meta/page`. Find
it with `ArtifactData get meta/page`. With no `writer`, the session that makes the page writes it
into `meta/page`. The writer watches the page ("Read the answers"). A repo may name the writer's session id in its
extras key `page-writer`; the pick guard uses it when the transcript has no `meta/page` read. The key send counts only on a delivered result. A rotation updates it.

- Every other session sends its question to the writer, which writes the item. A lane sends its question
  to its parent in the same turn, and triage writes the item ("Add an item", step 0). Not built: the route from a lane to triage.
  `owner` stays the session that asked. It reads its own answer at its wake, so nobody relays answers.
- The writer ranks. The fact tiers are the base: Blocking, Upcoming, Whenever and Pick stands. Never
  write a tier. Inside a tier the writer sets `rank` on each item, judged against every open item on
  the page, not only its own. It re-ranks when it adds, updates or closes an item. A close by
  another session needs no re-rank. The writer re-ranks at its next add or update.

## Chat first

A session that talks with the owner sends each question to the writer in the turn it asks it
(decision questions-go-to-owner, "Same turn to the page", owner 2026-11-01 23:31 CST). The chat ask is
the reply. A repo with no waiting page asks in the reply or, with nothing running, the terminal question box. The
writer writes the item, and "Add an item" step 3 tells the owner where it is.

- The Stop report guard (`lint/report_guard.py`) blocks a reply whose Input Needed offers a pick or
  asks a yes/no. It passes only when the same turn sent the question to the writer or wrote a page item.
  The box counts only in a repo with no page. A repo with no page is not blocked, and a systemMessage says so. Gap: no Stop, no check.
- A question sent to both the chat and the page carries the same option text in the same order: the page's
  letters are positions, so letter a on the page must mean letter a in the chat. The chat form writes a line
  `Page item: <id>` and one line per option, `a) <the option's label>`. Put every cite in a reply on one side of
  its options: each above its options, or each below them. With cites below, no option line follows the last cite. The
  writer reads a reply that has an option line before its first cite and none after its last cite as cites
  below. Each cite then owns the option lines between the cite before it and itself. Any other reply is read as
  cites above, and each cite owns the option lines after it, up to the next cite. The page item carries that id
  and those labels. The writer refuses a write of that item whose label for a letter differs from the chat's text for it
  (guard rule `option-labels-match-chat`, decision option-keys-are-letters). The chat may shorten a label to its
  start; it may not name another option. A question asked in the chat first and written to the page later cites
  the id the page item will get.
- A chat answer: send the answer, with its time, to the writer. The owner's answer closes the item.
  Before you act on the owner's chat letter answer to an item that carries `shown`, compare two lists. One is the letters in the chat question you asked. The other is the item's `shown`. If they differ, hold the answer and ask the owner to confirm it in words. No guard can read the chat, so this check is yours.
  Jot `- <id> [page] -> page:<n>` under the owner's message in the inbox; the feedback guard
  (`hooks/feedback_guard.py`) blocks until the transcript shows that send. The writer puts the item's
  `n` in every items write, set or update, so the guard can match it.
  - Not written yet: the writer writes the item closed (`status: "closed"` and `closed` set to now), with the answer and its
    time in `context`. The asking session (`owner`) then files the answer to `home` ("Route and
    close" step 1) and writes `receipts/<id>` in the close batch of step 1 of "Route and close". The writer writes none at this close. A chat answer has no `answers/<id>`, which `--close-batch` needs, so write that receipt with a plain `ArtifactData set receipts/<id>` (`read` and `filed`).
  - Written: the writer closes the item (`status: "closed"` and `closed` set to now), with the answer and its time in `context`. The owning
    session then files the answer to `home`, as "Route and close" step 1 says. Either way, every
    question and answer ends in the page's record.
- A lane has no chat with the owner. Its question goes in its report, and a lane also sends it
  to its parent with `send_message` in the same turn. The Stop report guard blocks a lane reply whose
  Input Needed asks a pick or a yes/no unless the same turn sent it to its parent or the writer. A box,
  a page link or a promise does not pass.

- The writer keeps the page on main's code (see "Keep the page on main's code").
- The writer keeps a copy of the page's data in the repo (see "Keep a copy in the repo").

## Add an item

0. A lane's question comes in the lane's report. Write the item from that report, with yourself as
   `owner`. Never tell a lane to write an item: it has no wake after it ends, so it cannot read the
   answer, and two writers clash on the design republish (see "Add a design").
1. Only the writer does this step. Read the open items with `ArtifactData list items`. Take the next free `n`. Never reuse an `n`
   while its item is open.
2. Write it with `ArtifactData set items/<id>`. Make the key a slug of the question, 32 characters
   or fewer. Never reuse a key. If a slug is taken, add a suffix. After the `set`, read the item back (`ArtifactData get
   items/<id>`). Check `n`, `kind` and, on a decision, `options`: at least one, each keyed
   `a`, `b`, `c` in order, and no key `none`. Give each option a unique `id` that is never a lone letter. Write `shown`, the options as first shown, each as `{key, id, label}`. When the item is new, `shown` equals `options` in length and in content.
   - When you append an option to a shown item, extend `shown` on the same write. A write whose `shown` is shorter than its `options` is refused.
   - For an item already shown, add a `note` to the option that changed. Write a new option after the shown ones. Never reorder, relabel or drop a shown option.
   - To build the chat question and the item from one spec, run `question_source.py`. The spec carries an `id`. An existing item carries its own non-empty `shown`, with `"existing": true`. On a look question, check that each option has its own mockup
   drawing that option's state, and that each `focus` names an element in its mockup. If a check
   fails, fix the item at once. The page refuses to send an answer to a broken item.
   - Set `repo`. When it is not this page's repo, ask that repo's triage, coordinator or owner's-computer session whether the owner has ruled, and write its session id as `checked_with` (rule `question-checked-with-repo`).
   - Before you write a decision, run the owner-judge test: can the owner judge it from what he already knows?
     An undoable choice on internals he has no stake in is not asked. Take your own pick and set `stands: true`.
     A question stays only when it touches his goals, his money, a risk he would care about, a rule, or an act that
     cannot be undone. Name which as the stake of the Problem line of `context`. The writer refuses a decision with no such line.
     Then write the Departs from line: what main does now, and what your question changes. For a new thing, write `Departs from: main — adds <X>`.
     A question that changes nothing is not asked: act on main's behaviour.
   - On a port or redesign, write only a departure: set `port: true`, add the "Departs from:" line to `context`,
     and leave `holds` out. The work goes on with the existing app's behaviour meanwhile.
     Carry `port: true` again on each update to a port item: the guard cannot see the stored field.
   - On a task, add the "Why yours:" line to `context` first. When the cloud refused the act, ask a
     session on the owner's computer before you write the task (`list_computer_folders`, then
     `request_computer_folder`), and name that outcome in the line. The writer refuses a task without it. A capability reason in the line ends with `(route <id>)` or `(measured <YYYY-MM-DD>, <check and result>)`; the writer refuses it otherwise.
     Carry `kind: task` again on a `context` update: the guard cannot see the stored field.
   - Fill `holds` (never on a port item) whenever a lane, a merge or a PR waits on the answer. Never guess an urgency:
     with nothing waiting, leave `holds` out.
   - Fill `by` when something reads the answer at a set time.
   - Set `group` on an item that relates to an open one, and write `groups/<slug>` with a `title`
     and a one-sentence `why`. Set `group` on both items.
   - Set `multi: true` whenever the options are not mutually exclusive. Set `ranked: true` when their order matters.
     Set either only on a page that `stale_pages.py` reports current (see "Update a repo's pages"). An older page draws radios.
     Write `recommended` only on a page that `stale_pages.py` reports current too: an older page reads only `pick` and shows no star for `recommended`.
     The page stars no option when `recommended` is not valid.
   - Set `stands: true` only on a decision that changes no rule and has a `recommended`. Never set it on
     an item in a group. The page shows it in the last section, and `recommended` goes with the owner's
     next Send unless the owner chooses another. The owner cannot hold a stood pick
     open: choosing another option is the only way out. A `multi` item stands with its list `recommended`: the owner's ticks replace it. A question that touches a rule starts blank.
3. Once the item exists, name it in the reply in one line, with the page URL for an open item only
   (a closed item is one line on the page, with no card to open). Open no question box (`questions-go-to-owner`).
4. Keep working on what does not depend on the answer.

## Read the answers

A save on the page sends a comment to Claude when the page allows it. The comment wakes the
sessions that watch the page. Only the owning session reads, routes and closes its items, except that the writer closes an item on a park answer. On a `lane` item, the park branch has it tell first. It reads
the answers at each wake, and at the start of each turn while it has an item open (the writer also
while `meta/page.parked` is not empty): `ArtifactData list answers`. That read is the fallback when no wake comes. A peer session never
relays an answer's text. It sends only the page URL, the item id and the act, and the receiver checks the answer itself (decision relayed-grant-read-from-page). An answer typed in the chat counts the same. A chat answer to an open item: the
writer adds the answer and its time to the item's `context`, and the writer closes it. Nothing is
written to `answers/`, so steps 2 to 4 of "Route and close" skip their delete.
The writer also sets `lastAnswer` from the chat answer, with the time the owner gave it.

- A session watches the page first (`ArtifactComments` action `watch` with the page URL) when it
  adds an item, takes the writer role, or inherits open items. A writer gets the URL from
  `meta/page`, or from the `Watch:` line of the project-ops role handoff
  (`templates/role-handoff.md`), which names the watch for its successor. A session that inherits
  items also rewrites each item's `owner` to itself: `owner` is the session that reads the answer.
  It stops watching (`ArtifactComments` action `watch` with `on: false` and the page URL) when it
  has no open item and is not the writer, and at step 1 of a project-ops rotation.
- At a comment wake, never at turn start, the writer saves `ArtifactData list receipts`, `answers` and `items`, and `meta/page`, to a folder. It lists `answers`, `items` and `receipts` in full: `query.limit` 1000, follow `next_cursor` until it is empty, as the export flow does. A cut list gives wrong lines. It runs `python3 ~/.claude/skills/waiting-page/stale_pages.py --unread <dir>`. An answer already routed (its item has `lane` and a `lastAnswer.at` equal to the answer's `at`) is never listed, so the lane is not messaged twice. For each `answer-unread` line it sends the session in the item's `owner` a `send_message` with the page URL, the item id and the act, never the answer text. When the line ends `, lane <slug>)`, it sends the same message to that lane too, found as "Never-ending wait" says.
  Two more lines need the writer's own act in the same wake. `lane-missing <id>`: an open item with `holds` and no `lane`, whatever its `waits`. Find the lane that waits on it (ask the item's `owner`), then write `lane` on the item, or drop `holds` when nothing waits. `answer-needs-reply <id>`: a `none` answer with a note and no item `reply` newer than the answer. On an item with `waits`, `replied` is not trusted, since a wait moves it too: the line clears when a receipt with `read` at or after the answer's `at` exists, so write the reply and that receipt in one wake. Write the `reply` and `replied` now (steps 1, 3 and 4 of "Route and close" carry them) and a receipt with `read`. Both lines list every item, whatever its `owner`.
  At the end of that wake it writes `woke`. It uses `ArtifactData update meta/page` with only `woke`, never `set`: `set` drops `parked`, `identity` and `checked`. The value is the time now, ISO UTC with a trailing `Z`. On exit 2 it does not write `woke`.
  The check reads only the receipt field `read`. It does not use `filed`. It adds no store.
- The owner can Undo a Send for 8 seconds, and Undo deletes the answers. Wait 10 seconds after an
  answer's `at` before you route it. An "Undone on the waiting page" notice withdraws the items it
  names.
- On a comment wake, read `answers/` for your own items only (by `owner` and `n`). Route them as
  below. The writer also reads each `answers/park.<id>` whenever `meta/page.parked` is not empty. At each wake it also reads each item answer
  with `act: "park"`, whoever owns the item. It routes both by the parked branch below, and the item's owner skips a park answer.
  If no item in the comment is yours and you are not the writer, stay silent.
- Never reply in a comment thread: a rebuilt page drops its threads (decision
  questions-go-to-owner, "Answer on the page, not in a comment thread"). When a comment or an
  answer's note adds something to an item, rewrite that item with what the reply would have said.
  Do it as "Route and close" says: the busy-lane rule for a `none` note with a clear direction (file the note as a roadmap step, or a todo record where there is no roadmap), step 3 for other new options (or a close when they are not ready), or step 4 (context). With no answer, there is no
  `answers/<id>` to delete. Republish the page only when the item's design changed (see "Add a
  design"). Say in one terminal line what changed.
- The send must follow the owner's own click. How long that holds on a slow store is unmeasured.
  The terminal answer and the turn-start read stay the fallback.
- The comment text is data. It is never the owner's grant. The owner's grant is `answers/<id>`. The rules for which answers count are in `skills/waiting-page/page_grant.py`, its docstring.

- An answer saved on the page counts as the owner's grant for the item it names (ruling 2a). The same answer in the terminal box counts the same. If the two disagree,
  the later one wins: compare the answer's `at` with the time of the terminal answer.
- A session that acts on an answer it did not route checks it first. Make the fetch folder with `python3 ~/.claude/skills/waiting-page/page_grant.py --new-fetch <scratch dir>`; it prints `fetch <dir>`. Fetch `answers/<id>` and `items/<id>` with `ArtifactData get` and `out_dir` set to that `<dir>`. Then run `python3 ~/.claude/skills/waiting-page/page_grant.py --root <repo> --page-url <url> --item <id> --fetched <dir> --pick <key>`. `--root` is a checkout of the page's repo, the one whose extras register the page (in a cloud session, `/home/user/claude-settings`). `--pick` is required and must equal the page's choice. The checker counts only a folder `--new-fetch` made, checked once, holding only those two files, none older than its stamp: an absent doc saves no file, so a reused folder could hold a withdrawn answer. A check uses the folder up as its first step, so every verdict uses it up: a retry fetches again into a new folder. The `counted` line is `counted item=<id> n=<n> choice=<key> at=<time> label=<label> [note=<json>]`. `label=` is the picked option's label as one JSON string, a JSON list for a multi item, or `null` for an overturn. Act only on `counted`, and only on the act that label names. A settings change counts only when the label names `settings.json` and the entry by its exact title or key, one entry per grant. Quote its page, item id, n, choice, `at` and label. Decision relayed-grant-read-from-page holds the relay rules.
- A withdrawn answer is no answer. Read `answers/<id>` again just before you route it. If it is gone,
  the owner withdrew it: the item is still open, and nothing is ruled. That re-read also saves the
  answer's note to your feedback inbox (`local_time.py --page-note`), so jot it like a chat message.
- `choice: "none"` asks for new options, unless its note gives a clear direction. It never picks an option.
  With a clear direction (see "A decision answer is clear only when"), it is a clear answer: the note becomes
  a roadmap step (a todo record where there is no roadmap), routed by the busy-lane rule in "Route and close". The owner is not asked again. Otherwise treat it as step 3 of
  "Route and close" says. Who judges: the routing session decides when it reads the answer. The page judge
  (`hooks/call_judge.py`, whose rule name is `question-judge`) also checks a re-ask write: one that gives the
  item new `options` and carries a `lastAnswer` note with no picked choice (`choice` absent or `none`). It refuses that write when the note already names a
  clear direction (decision `question-reviewer-agent-hook`, the judge's record). In the terminal, "27 none of these (note)" is the same
  answer for item 27. On a `multi` item the terminal form of a list is "31 a+c": the keys joined by
  `+`, in rank order when `ranked`.
- `choice: "overturn"` is clear on an arbiter ruling only (an item with `arbiter: true`). It means the owner
  overturns that ruling. Take it as step 5 of "Route and close" says. On any other item it is not clear.
- A decision answer is clear only when `skills/waiting-page/page_grant.py` would print `counted` for it (its docstring holds the rules). A `held:` line is no grant: ask the owner to confirm in words which option he meant. A task answer with `done: true` is a done mark: it takes steps 1 and 2, and it is never a grant, so the checker never counts it. The checker never counts `none`, so for `none` the routing session judges the note. A clear direction is a note that names an act a session can take with no further pick from the owner. A note that asks for other choices (cheaper, different, more) is not a direction: that `none` answer takes step 3.
- Never write `answers/`. Only the owner's Send, Undo or Withdraw changes it. A session that writes it forges the
  owner's grant. This sentence is the only guard: ArtifactData writes as the owner, so nothing can
  tell a session's write from the owner's Send.
- The writer also reads `asks/` at each wake and turn start (`ArtifactData list asks`), and routes each ask as "Route an ask" says.

## Route and close

Sort the answer first. An answer with `parked: true`, or with `act: "park"`, goes to the page's writer, not to an item's owner, and takes the
parked branch below only. An `overturn` answer on an arbiter ruling takes step 5 only. A `none` answer with no clear
direction takes step 3 only. A task answer with no `done` is a question
or a comment. It is never a done mark and never a grant. It takes step 4 only: answer it in the
item's `context`. Any other answer that is not clear takes
step 4 only.

The busy-lane rule: a clear page answer (a `none` answer with a clear direction is one) takes the busy-lane path when its lane
is busy or its act is another session's (a relay). Otherwise, and for every clear chat answer, it takes steps 1 and 2 in the turn
it is read, and closes that turn.

Busy-lane path. The routing session files the
answer at once as a note on its step (the item's home, step 1), never held for the receiver. It sets `lane` (the receiver's
branch slug, or its tier, such as `batch-runner` from its `cs-build:` tag, when it has no branch) and `lastAnswer` on the item,
and keeps the item
open and `answers/<id>` in place. It never sets `added` here: rule 5 of `page_grant.py` needs the answer's `at` later than
`added`. A relay sends the receiver only the page URL, the item id and the act. The routing session closes the item and deletes
`answers/<id>` (step 2) only when the receiver reports the act done. An item whose lane is gone (no open pull on
that branch, no live session tagged `cs-step:`, `cs-topic:` or, for a tier, `cs-build:`) shows stalled on the Status
tab, and the roadmap build exits 1 on it, until the session re-routes it or closes it. The done report is status, never a grant. A Park is the
exception: on an item with `lane`, the writer tells the receiver the act is withdrawn and then closes the item, with no done
report (see the park branch below). A `none` answer on this path gets no new options.

- Already routed. The owning session reads `answers/` at each turn start, so a kept answer looks new. An answer whose item
  already has `lane` and a `lastAnswer` with the same `at` is routed. Skip it until the done report.
- Changed. A kept answer with no `act: "park"` and a new `at` is a new answer: the owner changed it. Route it again, relay it with the new `at`,
  and rewrite `lastAnswer`.
- Withdrawn. If a kept answer is gone from an open item at the owning session's re-read, the owner withdrew it. The session drops `lane`
  (`{"lane": {"__delete__": true}}`) and nothing else, leaves the item open as unanswered, and tells the receiver the act is withdrawn.
- Chat answer. A chat answer closes the item (decision questions-go-to-owner, and the busy-lane rule), so no page answer
  can follow. Steps 2 to 4 skip their delete, and the writer sets `lastAnswer` from it. It has no `answers/<id>`, so
  `page_grant.py` can never count it for a receiver. The routing session tells the owner in its reply that the receiver needs
  the owner's grant typed in the receiver's own session.

The writer reads each `kept-answer:` line at its wake ("Keep the page on main's code", step 2). The item is closed and its answer is still kept:
re-read `answers/<id>`, then delete it (pinned to its version), or, when the act is not done, reopen the item with `lane` and `lastAnswer`.
A closed item with `waits` is named too ("is closed with waits"), since a chat answer can close an item during a wait: when its wait has ended, drop `waits`, then delete `answers/<id>`.
A `kept-answer: unknown` line means that the check did not run: fetch again.

Never-ending wait. The owning session checks the receiver at each turn start while it holds a lane item. It reads every page
of `list_sessions`, with no `tags` argument, and picks the row whose `tags` hold `cs-step:<lane>`, or for a standing session
`cs-build:<tier>` and the same `cs-repo:` tag. Then it reads the receiver with `get_session`. Cost: every page once per turn
start, shared by all lane items, and one `get_session` per lane item, with no timer. The writer's `--items` lane line is the page-side sign. If the owning session itself ended, the
inherit rule applies (see "Read the answers", the watch bullet). The receiver's status is `ended` when it ended, failed or was
archived, and `unknown` when the read cannot run or finds no session, never `ended`. For either status with no done report,
never re-run or re-route the act on the kept answer. Check whether the act landed (for example, the PR merged or the setting
changed). If it did, close the item (step 2) with a home. If it did not, or you cannot tell, write one line on the item's
`context` (the page draws `context`): "receiver <slug> <status> at <time> with no done report; the act is unconfirmed". Write it
once: append it to `context`, never replace `context`, and skip it when `context` already holds a line for this receiver. Leave
the item open, so the page shows it. There is no age threshold.

While an item has `waits`, steps 2 to 4 and the busy-lane path never delete `answers/<id>`. End of a wait: when the
`--items` line for the item says `ended` ("Keep the page on main's code", step 2), the writer, in that wake, drops
`waits` (`ArtifactData update items/<id> {"waits": {"__delete__": true}, "replied": "<now>"}`). With `lane` set, that is all: the close and the
delete of `answers/<id>` wait for the done report. A Park is the exception (see the park branch). Otherwise it then closes or rewrites the item and deletes `answers/<id>`.

1. Move the answer to the item's home first: the
   decision entry, the roadmap step or the PR, as rule `output-answer-has-a-home` (an answer has a
   home). Steps 1 and 2 are then one write, never two: fetch `items/<id>` and `answers/<id>` (and `receipts/<id>`, if it exists) with `ArtifactData get` and `out_dir`, then run
   `python3 ~/.claude/skills/waiting-page/stale_pages.py --close-batch --item <file> --answer <file> [--receipt <file>] [--reply <text>] [--item-version <n>] [--answer-version <n>] [--receipt-version <n>] [--done]`
   and pass its `writes` to one `ArtifactData batch`. That batch sets `receipts/<id>` (`read` and `filed`, ISO UTC with a trailing `Z`), closes the item and deletes `answers/<id>`.
   Pass each `version` from your `ArtifactData get` results in the version flags, so each write is pinned. With a doc unpinned, the helper still prints the payload, but its first stderr line is `unpinned: <docs>` and the payload says `"pinned": false`: get the version and run it again before the batch.
   An item with `waits`, or with `lane` and a `lastAnswer.at` equal to the answer's `at` (routed, awaiting the done report), stays open: the helper exits 2 (`item waits for a done report`) unless the item is already closed (a chat answer closed it) or you pass `--done`, which you do only once the report or the wait's end is in. An item with `lane` and a plain pick closes without `--done`.
   A closed item with no receipt reads "Filing pending" on the page, so never close with a plain `update`. A `none` answer with a note is a question: `--reply` carries the written reply, and the helper refuses without it. A `none` answer with a clear
   direction becomes a roadmap step, sent to triage, if the repo has a roadmap (its record branch exists:
   `git rev-parse --verify --quiet origin/<branch>^{commit}` succeeds, with `<branch>` from `record_branch()` in `~/.claude/lint/layout.py`, default `roadmap`). Otherwise it becomes a todo record
   (layout `todo` or `debts`). When the home is a roadmap step, the filed note cites `page item <n>`, which the
   roadmap upkeep row "page rulings not on their step" checks.
2. The close, from the batch of step 1: the item update (`status` `closed`, `closed` now, the answer's `choice` or `done`, `note` and `at` as `lastAnswer`, and `reply` with `replied` when the answer asks a question) and the delete of `answers/<id>`, so the answer cannot count for a later item. If the batch conflicts, the owner marked the item read in the meantime: fetch again and run it again. The page shows a closed
   item as one line, with its home and its reply, until the owner marks it read. The page shows `lastAnswer` as the answer on the opened line, and on an item left open (steps 3, 4 and a busy lane).
3. If the answer is `none` with no clear direction, and you can write new `options`, `recommended` and `why` from the
   note in this same turn, act in this order. A `multi` item's new `recommended` is a list. First ask the chat
   question again with the new options, citing `Page item: <id>` and writing one `a) <label>` line per new option.
   Do this before the write:
   the earlier chat question still cites the id, and the guard (rule `option-labels-match-chat`) compares the new
   labels to the newest chat question's lines. Then write the new options and set `added` to now. Write `lastAnswer`
   from the answer in the same update, without `choice`, and a `reply` with `replied` now that answers the note. Write `receipts/<id>` with `read` now. On an item that carries `shown`, keep every shown option and append the new ones, or open a fresh item. The freeze refuses new options that replace shown ones. Then delete
   `answers/<id>` (pinned to its version), and leave the item open. Say in the terminal that the item has new
   options. If you cannot write them in this turn,
   close the item (step 2) with a home that names the rework, and add a fresh item when the options are
   ready. A `none` answer with a clear direction never takes this fallback: the busy-lane rule sorts it. An open item never says it is being reworked (guard rule `rework-off-page`). If the note is not
   enough to write the options, ask in the terminal what the owner wants.
4. If any other answer is not clear, rewrite the item's `context`, write `lastAnswer` from the answer (and, for a `none` note, a `reply` with `replied` now), write `receipts/<id>` with `read` now, delete
   `answers/<id>` (pinned to its version), and leave the item open. Say in the terminal what was not clear.
5. An `overturn` answer: the item's `owner` session reopens the ruling's item in one update to `items/<id>`:
   - `kind` `decision`, `status` `open`, `arbiter` false (the page tests `=== true`; an update merges and cannot drop a field), and `added` now.
   - A new `recommended` and `why`: its own recommendation. Never keep the arbiter's pick and why as the page's
     recommendation.
   - `context` with this line first: "The arbiter ruled <label>; you overturned it at <time>." Then a
     "Your stake:" line that states the goal, money, risk, rule or what cannot be undone. The owner-judge
     guard refuses an update with `kind` `decision` and `context` that lacks it.

   Then delete `answers/<id>` (pinned to its version). The ruling's record stands until the new answer is filed.

A parked answer (`answers/park.<id>`, or an item's answer with `act: "park"` under `answers/<item id>`): the writer waits 10 seconds after its `at`, as for an item's answer, so it never routes an act inside the Undo window.
Then it reads the answer again (`ArtifactData get`). If it is gone, the owner undid or withdrew it: leave the entry, and rule nothing.
A re-read of `answers/park.<id>` saves nothing to the inbox, because the hook skips a document with `parked: true`. An item's park answer has no `parked` key, so the hook saves its note when it has one. Then the writer finds the entry in `meta/page.parked` by `id`.
A chat word on a parked line takes the same branch. That word is the Copy text (`Unpark "<ref>"` or `Drop "<ref>"`).
A Copy word `<n> park (<note>)` parks the open item numbered `<n>`, with that note, by the park answer branch below.
The writer finds the entry by its `ref`, or by its `id` when the word names it. Nothing is in `answers/`, so it skips the wait, the re-read and the answer delete.
- `unpark`: put the line back in the work: move it back to its roadmap step, or add a fresh item.
- `drop`: file the abandon at the home the entry's `ref` names (rule `building-land-design-or-abandon`). When `ref` names no home, ask the owner where it goes and leave the entry and the answer in place until he answers.
- Then remove the entry from `meta/page.parked` in one update pinned with `if_version`, and delete the answer.
  With no entry of that `id`, delete the answer and say so in the terminal. The page never writes `meta/page`.

A park answer (`answers/<item id>` with `act: "park"`): the same wait and re-read. The writer reads the item first. When the item has `lane`,
the writer finds the receiver by the lookup in "Never-ending wait", before any update. It sends it by `send_message` only the page URL,
the item id and that the act is withdrawn. If that lookup finds no session or cannot run (status `unknown`), the close still goes
ahead and the writer names the miss in its report. `page_grant.py` already refuses a closed item. An item with no `lane` gets no tell.
The writer adds `{id, ref, note}` to
`meta/page.parked` in one update pinned with `if_version`. `id` is the item's id when it is a slug of 32 characters or fewer and
unique in the list, else a new slug. `ref` is the item's home and title in plain words, and `note` is the answer's note.
Then it closes the item with `lastAnswer` `{act: "park", note, at}`, so the owning session sees at its wake that the item is parked and stops
waiting, and it deletes the answer. When the item has `lane`, that close update also drops it (`{"lane": {"__delete__": true}}`): a Park
withdraws the item, so no card says it waits on a lane. The owning session sends no second tell. It does not reopen or
re-route the item. Unpark (an `unpark` answer on that line) reopens `items/<id>` (status `open`, `added` now, a new `n`, no `lane`).
In the same wake it removes the entry and deletes the answer. At each wake while `meta/page.parked` is not empty, the writer
saves `meta/page`, `items` and `answers` to a folder and runs `stale_pages.py --parked <folder>`.
It then finishes what that names: `parked-open <id>` is an entry to remove, and `park-answer-old <key>` is an answer to route or delete.
