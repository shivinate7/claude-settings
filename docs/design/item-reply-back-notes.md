# Waiting page, step item-reply-back: reply to Claude's reply on an item (design notes)

Mockup: `docs/design/item-reply-back.html`. Screen: `skills/waiting-page/page.html` at main 5cc641f7. Its CSS (lines 8–908)
is copied whole into the mockup. Only `#newcss` is new.
Deep links: `#s=closed|open-empty|open-typed|open-over|just-sent|undone|waiting|answered|folded-waiting|failed|owed|owed-off|line-inside`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Each state is a `data-state` element in `#pics`.
Sizes: phone 390, mid 800 and wide 1280, as the brief names. `layout.py devices` prints `unknown` for this repo.
Themes: light and dark. In the frames, Reply opens the box and Close shuts it.
Why: owner on item 278, Nov 6 12:58 CST: he had to edit his old answer to answer back. Step item-reply-back.
This extends the ask reply (ask-reply-back-notes) to item cards. It is one home: the same box, Send, Undo, lock and line.

Settled by the brief (not options here): an item reply is a new `asks/<id>` record `{id, text, at, item}`, with no `re`.
The writer routes it to the item's `owner`, or takes it when that session has ended. The session answers on that ask record
(`reply`, `answered`), never on the item's `reply`. The record never shows in the Asks list, never counts in the ask pill,
and never makes a "Re: an ask not on this page" row. Dismiss stays ask-only. A new answer marks the card "New reply"
and opens a sunk card, as `replied` does today.

## 1. Which cards get Reply. Owner grant: yes

- Option "Answered and owed cards" (pick; `#s=owed`, focus `#pick-owed`). Every card whose thread shows the item's `reply`
  gets Reply at the thread's end: answered cards and owed cards. A ruling card has no thread, so it has no Reply.
  On an owed card the hint adds "No. 22 stays open: Mark done below answers it."
  - Gain: he can ask a question back on an item he still owes. Today the note box cannot do this without answering:
    a note with no pick sends as `choice: "none"` (a decision) or "Not marked done" (a task) (SKILL.md, `answers/<id>`).
  - Lose: an owed card has two text boxes: the note, which answers, and the reply box, which does not. The hint names the difference.
- Option "Answered cards only" (`#s=owed-off`, focus `#pick-answered-only`). Only an answered card with `reply` gets Reply.
  - Gain: one text box per owed card. Lose: a question back on an owed item still goes in as an answer.
- Departs from the brief: it named answered items only. The pick adds owed cards. Not blocking.

## 2. Reply, the box and the hint

- State `closed`. Reply (`.btn.alt.replybtn`, 44 px) sits at the end of the item's thread, start-aligned. It is today's ask Reply.
  Its hidden words name the item ("Reply on No. 41"), since the page now holds more than one Reply.
- Where the thread's end goes:
  - On a sunk card, it sits inside the open fold, after the thread. A folded card shows no Reply.
  - On an answered card in a tier, it sits after the thread.
  - On an owed card, it sits after the thread, above the context. `buildCard` draws the thread there today.
- States `open-empty`, `open-typed`, `open-over`. Reply opens today's `.replyform` in place, with focus in its textarea.
  It has today's label, Close, Send reply and the 4000 limit words.
- Hint: "Your reply goes to <writer>, which passes it to the session that asked No. <n>, or answers here. Ctrl+Enter sends."
  The ask words say "the session that answered". That is wrong on an item: the item's `owner` asked, so the item words name it.
  An empty box starts "Send reply turns on once you type."
- Close keeps the words as a draft (ux-keep-what-was-made), as today.
- A fold press on a sunk card hides an open box, as Close does. It keeps `rp.open` and the words, so the next unfold shows the box as it was.
  - Gain: the fold acts the same everywhere. Lose: for a moment the typed box is out of sight.
  - Other option, not drawn: lock the fold while the box holds words, with new lock words such as "Stays open: your reply is in the box".
    Gain: the words never hide. Lose: a fourth lock reason. Today's lock words ("your answer is ready") would be wrong for a reply.
  - Pick: no lock.

## 3. Send, Undo and the one lock

- States `just-sent`, `undone`. Send reply writes one `asks/<id>` record: `{id, text, at, item: "<item id>"}`.
  - The box closes, and his reply shows in the item's thread at once as waiting (item 4).
  - The line says "Sent 13:05. A wake was sent." with "Undo send (7)". These are today's `.sline` and `#askUndo`.
  - Undo deletes the record and puts the words back in the reply box, which reopens. The line says "Undone. Your reply is back in the box, not sent."
- One lock, `askState.sent`: while any Undo counts, Send ask and every Send reply (on an ask or an item) are off, with today's words.
  `just-sent` draws it on the Ask box. Send answers in the bar has its own Undo and is not locked by a reply.
- Wake comment (pick), through `canTell` and `notifyClaude`, cut at `ASK_NOTICE` and `MAX_BYTES`:
  - Send: "Replied on the waiting page. Writer: <writer>. Ask <id> on item No. <n>, owned by <owner>: <text>."
    - `<owner>` is the item's `owner`.
    - Gain: the brief's words. No. <n> is the number the owner and a chat answer use.
  - Other option: also name the item id, as "on item No. <n> (<item id>)".
    - Gain: the writer could route before it reads the record.
    - Lose: the comment is longer. The writer reads the record anyway after the 10-second Undo wait ("Route an ask"), and the record holds `item`.
    - Pick: the brief's words.
  - Undo: "Undone on the waiting page. Ask <id> is withdrawn." These are today's words. "No comment" uses today's `NOT_TOLD`.

## 4. Where the line and Undo sit. Owner grant: yes

- Option "Under the thread" (pick; `#s=just-sent`, focus `#pick-under`). The line and Undo sit in `.replyend`, under the thread box,
  above Reply, as on an ask. `.replyend` is a sibling after `section.thread`.
  - Gain: one look for one act on asks and items (ux-variant-extends-home). The answer shows where Reply was (ux-answer-at-press).
  - Lose: on a sunk card, the line sits outside the grey box that holds the conversation.
- Option "Inside the thread box" (`#s=line-inside`, focus `#pick-inside`). `.replyend` is the last child of `section.thread`, under a rule.
  - Gain: the conversation and its act read as one box. Lose: a second look for the ask's thread end. The reply box's `--ground` sits on `--chip`.
- Departs from: nothing on main. Not blocking.

## 5. The thread: his reply and the session's reply to it

- His reply sits inside `section.thread`, after the item's `Reply:`, as today's `.myreply` inset ("Your reply, <day, time>").
  The session's answer follows it, then his next reply, oldest first. Records join by `item`, sorted by `at`, ties by id (as `askAll`).
- The item's own `reply` stays above, unchanged. The session never writes over it, so nothing earlier is lost.
- State `waiting`: "Read by lane page-upkeep 13:07. Waiting for its answer." or "Waiting for triage to read it." (today's `askWaitWords`).
  Reply stays at the end while a reply waits, for a second thought.
- State `answered`: the session's words read "Reply from <owner>, <day, time>", then the text.
- Words (ux-one-plain-name). On an item card, "answer" is the owner's word ("Your last answer", "Answered", "You chose").
  So the session's words to his reply read "Reply from", not the ask thread's "Answer from".
  - "Reply" as a noun is a message back, and the lhead says whose: "Reply from <owner>" or "Your reply". The button "Reply" is the act, with one name on asks and items.
  - Other option, not drawn: also redraw the item's own `Reply: <text>` as "Reply from <owner>, <replied time>", so each session message has one form.
    - Gain: one form in the thread, with who and when. Lose: it changes every card that has a reply.
    - Departs from: page.html `threadEl` ("Reply: " + text) and SKILL.md ("The card shows it as Reply: <text>"). Not blocking.
  - Pick: keep main's `Reply:`.
- Fold words of a sunk card name his replies too (state `folded-waiting`):
  - The parts are: "your note", "your last answer", "the reply", and "your reply" once he has one.
  - "The reply" becomes "the replies" once a session has answered one of his.
  - For example, "Show your note, your last answer, the reply and your reply".

## 6. A waiting reply never hides; a new answer marks the card

- State `folded-waiting`: the next load, with nothing new, so the sunk card folds. Under the fold control, outside the fold, `p.fwait` shows
  three things, as on a folded ask: the half disc, "Your reply: <text>" (one line, two on a phone) and its state line.
- State `answered`: an `answered` on one of the item's reply records counts as a new reply. The card takes "New reply"; a sunk card opens at load,
  or in place while the page is open (page-reply-uncollapse-notes items 3 and 4). Nothing re-sorts.
  - Builder: `newReply(it)` also reads the newest `answered` of the item's reply records, against the same baseline.
- Not drawn: an answer that arrives while the card is folded by a press this visit. `.fwait` turns to the check and "Reply from <owner>, <time>.
  Show <fold words> to read it." The press wins for the visit, as today.
- Known gap: `newReply` needs `state.sendAt !== null`. An owner who has never pressed Send answers gets no mark on any card, from either source.
  This is today's rule, not new.
- The Asks list and the ask pill are unchanged. `waiting` and `folded-waiting` label the list: an item reply never shows or counts there.

## 7. Failure

- State `failed`. The hint (bad) says "Not saved (permission-denied). Your reply is still in the box: copy it and paste it in chat."
  Copy reply shows in the slot. Send reply stays on and tries again.
- Copy reply copies "re No. <n>: <text>". It matches the ask form ("re <ask id>: <text>"), with the number the owner uses in chat.
- Not drawn: no store (`state.db === false`). The page draws no item cards, so no Reply shows.

## 8. Keys, ids and the draft (pick)

- One key per item: `k = "item." + <item id>`. Every id and the draft key derive from it, through today's code:
  - `form.id.slice(3)` in `syncReplyForm`, `repOf(k)`, `replyDraftKey(k)`, `askState.sent.where`, `.replyend[data-end]`, and `$("rt-" + where)` in `syncUndo`.
- So: `#reply-item.<id>` (Reply), `form#rf-item.<id>`, `#rt-item.<id>` (textarea), `#rh-item.<id>` (hint), `#rx-item.<id>` (Close),
  `#rs-item.<id>` (Send reply), `#rc-item.<id>` (Copy reply). The draft is `localStorage` `waiting.replyDraft.item.<id>`.
- It cannot collide: every ask id starts `ask-`, and an item id never holds a dot (SKILL.md, `answers/park.<id>`).
- Other option: the brief's `rf-i<id>`. Lose: its draft would be `waiting.replyDraft.i<id>`, not `.item.<id>`, unless the builder adds a special case.
- The ids hold a dot. The page finds them with `getElementById` and `CSS.escape`, as today. A raw CSS `#rf-item.x` selector would break.

## 9. CSS for the builder

- `.myreply`, `.replyend`, `.replyform` and `.fwait` exist on main, but scoped to `.askc`. Drop `.askc` from those home rules
  (`.askc .thread .lhead/.reply/.myreply`, and `.askc.folded .fwait` widened to also take `.card > .fwait`). Do not add a card copy (ux-variant-extends-home).
- `.thread .reply` then also matches today's `p.ctx.reply`. It sets the same three values as `.ctx`, so nothing changes.
  The `closed` state labels that thread "Today:".
- New: `.card > .fwait { padding: 0 4px }`, since the card pads its own edge. Only option "Inside the thread box" adds `.thread > .replyend`.

## 10. Work outside this folder (for the builder and the writer)

- page.html:
  - `askAll`, `askThreads` and `askWaiting` drop records with `item`.
  - `threadEl` draws the item's reply records and ends with `.replyend`.
  - `sendAsk(k)` writes `{text, item}` for an `item.` key; `copyReply` writes the item form.
  - `openReply`, `closeReply`, `sendAsk` and `undoAsk` repaint the card (`repaint(it)`), not only `renderAskList`.
  - A card rebuilt on a push keeps the reply box's focus and caret.
  - The card's `signature()` includes its reply records.
  - Ctrl+Enter in the box and the answer bar ignore the item reply.
- SKILL.md "The database", `asks/<id>`: it says asks are "never an item". Add `item`: written once at Send, never with `re`.
- SKILL.md "Route an ask": an ask with `item` goes to that item's `owner`, or the writer takes it. It is answered with steps 1 and 2.
- SKILL.md "Route and close": a writer never closes an item while one of its reply records has no `reply`. The page would hide that reply:
  it has no Asks row and no orphan row. Owner grant: yes.

## Checked

- Playwright, Chromium (headless): 13 states at 390, 800 and 1280, light and dark (78 runs).
  - Result: no script error or console error, no sideways scroll in the page or the frame, no element past the frame edge.
  - Every Reply, reply-box button, live Undo and fold control is 44 px or taller.
  - The check went red on a broken copy (a 900 px thread, a 30 px Reply): 1648 misses.
- `check_designs.mjs` on main's page, with this mockup in `designData`. Each pick ran as a two-option item:
  - Pick 1's test item used `owed` / `#pick-owed` and `owed-off` / `#pick-answered-only`.
  - Pick 4's test item used `just-sent` / `#pick-under` and `line-inside` / `#pick-inside`.
  - Both exited 0 with `problem: null`.
- `label_once.py` on the frame HTML at 390 (labels off) of `closed`, `just-sent`, `answered`, `folded-waiting`, `owed` and `failed`: no hit.
- impeccable critique ran single-context, because no agent tool was open. The guard refused the context launcher, so it read the docs directly.
  The detector found nothing, but it reads only the static markup, not the screen the script draws.
  - Fixed: a "New:" label on the small New reply mark was clipped to "a new …". It is now dropped, and the caption carries it.
  - Open:
    - Fold words with four parts wrap to two lines at 390.
    - The widened home `.thread .reply + .myreply` spaces siblings with a margin, against ux-gap-on-parent (guidance). It is main's rule, kept as is.
    - The owed card holds two text boxes (item 1).
