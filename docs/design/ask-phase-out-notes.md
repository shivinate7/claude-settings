# Waiting page, step ask-phase-out: one line, then Mark read (design notes)

Mockup: `docs/design/ask-phase-out.html`. Screen: `skills/waiting-page/page.html` (main 6e8d6ccf9). Its CSS (lines 8 to 914)
is copied whole into the mockup. Only `#newcss` is new, and each new rule reads a page token.
Deep links: `#s=page|show|marked|read-lists|back|failed|all-read|today|rail-chips|rail-none|mark-all|keep-dismiss|fresh-opens`,
`&w=all|390|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Each state is a `data-state` element in `#pics`.
Sizes: phone 390 and desktop 1280, from the brief. `layout.py devices` prints `unknown` for this repo. Themes: light and dark.
Options are named by name, never by a letter.
The mockup is not yet updated: it still draws a "No home named" pill on an ask with no home, and a "Count only" rail. Where it differs, this file is the design.

Rulings: owner pick a on item 480 (09:14 CST Nov 10) with his read-receipt note; his comment on the Answered row (09:13 CST);
his question "where was this question?" (10:51 CST). The shape is the step's: once routed, an ask or an answered item shows one
line, its home and the short reply; Mark read removes it; nothing is deleted.

## 1. One read mark, and it is the ask's Dismiss. Owner grant: yes

- What: the page already has one "the owner has seen this, take it away" mechanism: Dismiss on an ask (ask-dismiss-notes 1 to 4).
  It writes `dismissed` (ISO time) on the root ask with `update`, hides the thread, and keeps the record. It shows the thread again when a record
  in it waits or gets a later answer. It lists the thread under "Show N dismissed asks" with Restore. Mark read is that mechanism, extended to items.
- Pick: one name for the act on asks and items: "Mark read", with "Mark unread" in place of Restore, "Marked read." in place of
  "Dismissed.", and "Show N read asks" in place of "Show N dismissed asks". The stored field keeps its name, `dismissed`.
  Gain: the owner's grant, and one act with one name on the page (ux-one-plain-name). Loss: an act he learned on Nov 6 changes its words.
- Option "Words: Dismiss and Restore" (`#s=keep-dismiss`, focus `#line-212`): today's words on both. Gain: nothing to relearn.
  Loss: "Dismiss" reads as "throw away", but nothing is thrown away.
- Not used: the `read` field. On `receipts/<id>` and on `asks/<id>` it means "a session read this". The owner's mark in the same name
  would give one word two meanings. Not used either: `receipts/<id>`, which only the owning session writes, and which Undo deletes
  (page.html line 2252); `answers/<id>`, which is the owner's grant and is deleted at close; browser storage, which another device cannot see.
- Departs from: SKILL.md "The database" (`receipts/<id>`, `asks/<id>`) and `askPress`/`dismissBtns`/`restoreBtn` words in page.html. Not blocking.

## 2. What counts as routed, and so shows one line

- Ask thread: routed when its root has `reply` and a `home`, and no record in the thread waits (`askRouted`). The line shows the `home`.
  An ask with no `home` is not routed. It stays a full card: a new answer in full, a seen one behind "Show N older asks" (pick 480 a).
- Open answered item: routed when it has a receipt with `filed` (`rcOf(it).filed`), and no `waits` and no `lane` (`routedOpen`).
  An item with a `lane` keeps its card, even when filed. The home is the item's `home`.
- Closed item with a `closed` time (point 5): always routed, with or without a `home`. A line with no `home` shows the pill
  "No home named" on a dashed edge, so a gap in an item's routing shows. A ruling (`arbiter: true`) is not a line: it keeps "Arbiter rulings".
- Everything else keeps today's look: "Filing pending" (No. 214 in `#s=page`: today's folded card with Change, no Mark read), an item
  answered by its wait (`waits`), an item on a lane, an owed item, and an ask or reply that waits.
- The short reply: the first sentence of `reply`, cut at 120 characters ("No." before a number does not end a sentence). A closed item
  with no `reply` shows "No reply. Closed <time>." (No. 201).

## 3. The line

- What: the ask's folded row with its side press (`.askc.folded.withd`), extended with `.rline`. One component for asks and items
  (ux-variant-extends-home). The row button holds two text lines: "No. <n>", the item's `short` (else its title), the home pill;
  then the short reply in `--muted`. Mark read is the side press, a sibling of the row button, never inside it. Its name is
  "Mark read: No. 212, Asks leave the Ask area" (`askPress`'s form). "Marking…" shares its box (`.fixw`), so a press moves nothing.
- The home pill: `--chip` ground, `--line` edge, its word "Home: " in a `.sr` span. The section sub carries the words once.
- An item line sits in the Answered section, in today's place and order (newest answer first; a closed item with no answer at its
  close time). A card that gets filed while the page is open turns into its line in place, so nothing jumps (ux-order-holds-still).
- Phone 390: the row wraps to three lines, "Show answer" stays in the row button's name only (today's `.withd` phone rule), and the
  whole row is the press.
- Press the row (`#s=show`): the line opens in place as the open ask card's shape: number, home, Fold; the title; the owner's answer
  and note, the full reply, and where it went ("Closed Nov 10, 10:40 CST. The record stays in step ask-phase-out."). An open item keeps
  Change; a closed one has none. The ask's opened line links its home when the home names an item on the page ("item 212" goes to
  `#line-212`). That answers "where was this question?".
- Option "A new answer opens" (`#s=fresh-opens`, focus `#askList`): a new answer draws as today's open card, not as a line. Gain: the
  whole answer shows with no press. Loss: the area grows with each new answer, which is the crowding the owner named.

## 4. Mark read, Mark unread, and the read lists

- Press Mark read (`#s=marked`): the line becomes today's Dismissed line in its place, reworded: "Marked read. No. 212, Asks leave the
  Ask area" with Mark unread. It stays until the next load, then it is gone (ask-dismiss-notes 3, no count: nothing races a read mark).
  The section count and the rail's Answered count drop by one at once, and the item's chip leaves the rail.
- Read lists (`#s=read-lists`): "Show N read items" ends the Answered section; "Show N read asks" ends the Ask list (today's
  dismissed fold, renamed). Each opens its list on a dashed edge, newest mark first, with a quiet Mark unread on each row.
- A read item comes back as a line when the writer's `replied` is later than its `dismissed` (`#s=back`, No. 209: marked 10:00, a
  reply at 11:25; it carries the New reply mark). A re-ask is owed work: it draws as an open card in its tier, whatever `dismissed`
  says (No. 198 in Upcoming). So an owed item is never hidden. The ask rule stays as today (`askDismissed`).
- Failure (`#s=failed`): the line stays; under it, "Not marked read (permission-denied). It stays on the list." Mark read stays on and
  tries again. Mark unread that fails: "Not marked unread (<code>). It stays read."
- All read (`#s=all-read`): the section keeps its head with count 0, one sentence "All read.", and the read-items fold. The Ask list
  keeps its waiting asks and the read-asks fold.
- Option "Mark all read" (`#s=mark-all`, focus `#tier-answered`): one button at the end of the Answered lines ("Mark all 4 read") and
  of the ask lines. Gain: one press clears the area. Loss: a batch write, and it marks replies he never opened.

## 5. Which closed items show: the flood rule. Owner grant: yes

- Departs from: main (closed items leave the page) — a closed item that carries a `closed` time stays as one line in Answered until
  the owner presses Mark read. An item closed before this ships has no `closed` time and counts as read, so none of the 485 old items comes back.
- Measured: the roadmap branch's `waiting/items/` holds 485 records; items 480 (`ask-phase-out-rule`) and 302 (`zizmor-pin-move`) are
  closed with no close time. So the page cannot tell an old close from a new one today, and a new field is needed.
- Asks: a routed ask (point 2) whose newest `answered` is before the ship time counts as read and goes behind "Show N read asks". The
  page holds the ship time as one constant, `READ_FROM`. An ask with no `home` is not routed, so this rule does not reach it: it keeps
  its full card, and a seen one stays behind "Show N older asks" (`ASK_SHOWN`). Departs from: page.html `ASK_SHOWN`, for routed asks
  only (they leave that fold and show as lines). Not blocking.
- Section sub, rewritten so it is true (ux-statements-are-true): "Your sent answers, newest first. Each line leaves when you mark it read."
  Today's "Each leaves the page once its session closes it." would be false.

## 6. The rail's Answered row

- The rail keeps its chips (`#s=rail-chips`). The Answered row lists one chip per item in the section, and its count is the section's
  size, closed lines included. A chip leaves when its line is marked read, and the count drops by one with it.
- Option "Rail: no Answered row" (`#s=rail-none`): the row is gone; the section stays. Gain: the shortest rail. Loss: nothing on the
  rail says answered lines wait.
- Dropped: "Count only" (the head and a count, with no chips). The rail keeps its chips (coordinator's direction, 2026-11-10 13:29 CST).
- The Ask row stays as today: it counts asks that wait for an answer.

## 7. New stored fields (outside this folder, for the builder)

- `items/<id>.closed`: ISO UTC time with a trailing `Z`, written by the session that closes the item, in the same `update` as
  `status: "closed"` (SKILL.md "Route and close" step 2, and the writer's "written closed" path for a chat answer).
- `items/<id>.dismissed`: ISO time, or `null` after Mark unread. Written only by the page, with `update`, at the owner's press. No
  session writes it. This is the page's first write to `items/`: SKILL.md "The database" and "Every other closed item stays hidden" change.
  A writer's `set` on a re-ask drops it, which is right: the item is owed again.
- Both go into page.html's `itemFields` block, which the guard (rule `item-field-rendered`) reads too.
- `asks/<id>`: no new field. `dismissed` exists.
- Page constant: the ship time for asks (point 5).
- A session changes a closed item only with `update`, never `set`, as for asks. A `set` drops `closed` and `dismissed`, and the item
  then counts as read and leaves: the item 480 incident again. The path is real: item 480's `reply` was rewritten after it closed.
- A Mark read on an open item (lane or filed) changes the item's version. The pinned close of step 2 then conflicts. The session
  re-reads and retries the close; it never drops it.
- Order of landing: `closed` and `dismissed` are in `itemFields` on main before any session writes them, or the guard refuses the close.
- A check the design needs: a close with no `closed` time breaks it. The writer's read of closed items (the `kept-answer:` lines of
  "Keep the page on main's code" step 2) can flag a closed item with no `closed` time that changed after the ship time.

## 8. Critique pass (impeccable, single context; no agent tool, no snapshot)

- Fixed: item lines said "Show" and ask lines "Show answer". Both now say "Show answer" (one act, one name).
- Fixed: in the read lists, Mark unread was the loud `.btn.alt` on every row, louder than Mark read. It is quiet there. The one
  Marked read line keeps `.btn.alt`, as today's Restore.
- Note, not fixed: a filing-pending card (green ground, full card) is now the loudest thing in Answered, though it needs nothing from the
  owner. It is today's card, outside this step.
- Question for the owner: should a filing-pending answer fold to a line too (no Mark read until it is filed), so the section is
  all lines? Not drawn.
- Detector: no finding. It reads the page markup only, not the screen the script draws, so its clean result proves little.

## Checked

- Playwright, Chromium, picture mode: 13 states at 390 and 1280, light and dark (52 runs). No script error, no sideways scroll;
  focus ids `rail`, `line-212`, `tier-answered` and `askList` each find a box.
- `check_designs.mjs` on main's page with this mockup in `designData`, for the four owner questions (rail, words, Mark all, new answer):
  each `{"problem": null}`.
- `label_once.py` on `page` and `read-lists` at 390: no hit. It skips text in controls, so the repeated "Mark read" buttons do not count.
