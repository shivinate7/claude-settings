# Waiting page, step ask-reply-back: reply to an answered ask (design notes)

Mockup: `docs/design/ask-reply-back.html`. Screen: `skills/waiting-page/page.html` at main 2824190a. Its CSS
(lines 8–815) is copied whole into the mockup. Only `#newcss` is new.
Deep links: `#s=closed|open-empty|open-typed|open-over|just-sent|undone|waiting|answered|re-row|folded-waiting|failed|offline`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Each state is a `data-state` element in `#pics`.
Sizes: phone 390, mid 800 and wide 1280, as the brief names. `layout.py devices` prints `unknown` for this repo.
Themes: light and dark. In the frames, Reply opens the box and Close shuts it.
Ruled data shape: roadmap step ask-reply-back. A reply is a new `asks/<id>` record `{id, text, at, re}`. It goes through
today's Send path: the 8-second Undo, the "Send waits until Undo ends" lock and the wake comment.

## 1. Reply control: closed and open

- State `closed`. An unfolded answered ask gets one `.btn.alt` "Reply" at the thread's end, under `.thread`, start-aligned, 44 px.
  A folded row has no Reply. "Show answer" first, so the owner reads the answer before he answers it.
- States `open-empty`, `open-typed`. Reply opens the reply box in place, focus in its textarea. It reuses `.askform` and `.askrow`
  on `--ground`: label "Your reply", the textarea, the hint, Close (`.btn.quiet`) and Send reply (`.btn.askgo`, dashed when off).
  No Add to list: a reply sends only itself, and never takes the Ask box's list or box.
- Hint: "Your reply goes to triage, which passes it to the session that answered, or answers here. Ctrl+Enter sends."
  With an empty box it starts "Send reply turns on once you type." The UI never says the reply goes straight to the owner session.
- Close keeps the words as a draft (ux-keep-what-was-made), kept in `localStorage` `waiting.replyDraft.<root id>`. Reply reopens them.
- Ctrl+Enter in the reply box sends the reply, never the ask or the answers.
- State `open-over`. Over 4000 (`ASK_MAX`), nothing is cut. Send reply is off. Hint: "Your reply is 4213 characters. The limit
  is 4000. Shorten it, then send. Nothing was cut." These are today's ask words.
- Departs from: nothing new. Opening the box grows the card in place, as Change already does on an answered card
  (answered-sink-notes item 4). Content below moves down.
- Other option, not drawn: the box always open on every answered ask. Loss: every answered card grows by a form.

## 2. Send and Undo

- State `just-sent`. Send reply writes one `asks/<id>` `{id, text, at, re}`. The box closes. The reply shows at once in the thread
  (item 4) as waiting. The line under the thread says "Sent 17:50. A wake was sent." with "Undo send (7)". This is today's `.sline`
  and `#askUndo`, at the reply, not at `#askLine` (ux-answer-at-press). Reply shows under the line.
- One lock: the Undo slot is `askState.sent`, one for asks and replies. While either Undo counts, Send ask and every Send reply are off,
  with today's hint "Send turns on when the Undo count ends." (Send reply: "Send reply turns on when the Undo count ends.")
  Drawn on the Ask box in `just-sent`.
- State `undone`. Undo deletes the record. The words go back into the reply box, which reopens. The line says "Undone. Your reply is
  back in the box, not sent." Departs from: `undoAsk`, which puts asks back in the stack. A reply has no stack. Not blocking.
- The line stays until reload or the next Reply press. After the count, Undo keeps its box hidden (`.spent`), as today.
- Wake comment, through `canTell` and `notifyClaude`, cut at `ASK_NOTICE` (500) and `MAX_BYTES`:
  - Send: "Replied on the waiting page. Writer: <writer>. Ask <id> re <re id>, answered by <owner of re>: <text>."
  - Undo: "Undone on the waiting page. Ask <id> is withdrawn."
  - No comment: today's `NOT_TOLD` words.
  The comment wakes the writer. It names the parent's owner only so the writer can route; the writer does the routing.

## 3. What `re` names. Owner grant: yes

- Pick: `re` is the id of the record whose answer the reply follows: the newest answered record in the thread. For a first reply
  that is the root ask; for a reply to a reply's answer, it is that reply. Its `owner` answered last, so the writer routes there.
- Other option: `re` always names the root ask. Gain: a flat thread, one lookup. Loss: a reply routed to another session
  (its `owner` differs from the root's) would route back to the root's session, not the one that answered.
- A reply can be replied to: Reply always sits at the thread's end, also while a reply waits (state `waiting`). A second
  reply then names the same `re`.
- A record whose `re` is not in the map still shows, as its own row with "Re: an ask not on this page". It never vanishes. Not drawn.

## 4. Where a reply sits: nested in the thread (pick)

- Option "Nested in the thread" (`#s=answered`, focus `#pick-nested`). The reply sits in its root's card, inside `.thread`, after
  the answer it follows. It sits in a `.myreply` inset on `--surface`, the ground of "You asked". So the owner's words and a
  session's differ by ground. Its answer follows it as today's `.lhead` and `.reply`. The card keeps its place, ordered by the root's `at`.
- Why: the thread reads top to bottom in one card. The reply appears where Reply was pressed. The parent never moves. A
  reply to an old ask is never split from it. Loss: the card grows; rows below move down. Their order holds, so
  "a reply never moves a row" (page-ask-box-notes item 8, ux-order-holds-still) is kept; the growth is the Change precedent (item 1).
- Option "Own row, Re: link" (`#s=re-row`, focus `#pick-rerow`). The reply is its own row at the top (newest first by `at`), with
  a `.reline` link "Re: “<parent text>”" to `#<parent id>`. Gain: one record, one row, no grouping. Loss: the thread splits;
  the parent may sit behind "Show N older asks", so the link must open it; two Reply buttons per conversation.
- Hide controls: "Nested in the thread", "Own row, Re: link". `check_designs.mjs` passes on both pictures (item 9).
- The waiting page stamps its own letters, so no option has one.

## 5. A waiting reply never hides

- State `waiting`: same visit, the writer routed the reply; `.myreply` says "Read by lane tier-fold 17:52. Waiting for its answer."
  and "waited under an hour" (today's `waited`). Waiting, not read: "Waiting for triage to read it." Today's `askItem` words.
- State `folded-waiting`: a later load. The root's answer was seen, so the card folds. The `.frow` button stays one button. Under it,
  outside the button, `p.fwait` shows the half disc, "Your reply: <text>" (one line, two on a phone) and its state line.
- A thread with a waiting reply counts as waiting in the `shown` filter of `renderAskList`: it is never behind "Show N older asks".
  Drawn: the thread is older than the three seen answers shown, yet shows above "Show 4 older asks". Rows keep their order.
- An answer that arrives while the row is folded: `.fwait` turns in place to the check and "Answer from <owner>, <time>.
  Show answer to read it." The card stays folded until a press; a fold changes only at a load or a press (today's rule). Not drawn.
- A thread opens on load when any answer in it is new (`askFresh` over the thread's newest `answered`), with "New answer".
- Count: `askWaiting()` already counts each record with no `reply`, so a waiting reply counts in the Ask pill and the rail row.
- Builder: `askAll()` and the `shown` filter work on threads. Records with `re` leave the top level and join their root.

## 6. Failure states

- State `failed`: the write fails. The box keeps the words. Hint (bad): "Not saved (permission-denied). Your reply is still in the box:
  copy it and paste it in chat." Copy reply shows in the slot. Send reply stays on and tries again.
  Copy reply copies "re <re id>: <text>", the form the step note gives for a manual reply.
- State `offline` (`state.db === false`): today's list text "Your asks cannot be read in this view." No answered ask shows,
  so no Reply shows. The Ask box's Copy ask is the way on, as today. Departs from the brief: it asked for a reply box with Copy
  in this state, and the page cannot draw one there. Not blocking.

## 7. Selectors and ids for the builder

- Per thread, keyed by the root ask id `<k>`: `#reply-<k>` (Reply, `aria-expanded`, `aria-controls="rf-<k>"`, `data-ask`),
  `form#rf-<k>.askform.replyform`, `#rt-<k>` textarea, `#rh-<k>` hint (`aria-live="polite"`), `#rx-<k>` Close, `#rs-<k>` Send reply,
  `#rc-<k>` Copy reply. The line: `p.sline` (`role="status"`) in `.replyend`; its Undo keeps id `askUndo` (one Undo at a time).
- `.myreply` (id = the reply's ask id), `.replyend`, `p.fwait` in `li.askc.folded`, `.reline` (option "Own row" with its link, and, with no link, the orphan notice of section 3).
- `askState.sent` gains `where`: `"box"` or the root id, so `renderLine` draws the line at the right place.

## 8. Sizes and themes

- 390: the hint takes its own row (today's 66 px reserve). Close and Send reply share the next row. `.fwait` text clamps to two lines.
- 800 and 1280: today's one-row `.askrow`. All new targets are 44 px or more (Reply 44, Close and Send reply 48).

## 9. Checked

- Playwright, Chromium: all 12 states at 390, 800 and 1280, light and dark (72 runs). No script error, no sideways scroll in the page
  or the frame, no element past the frame edge, every new control 44 px or taller. The check went red on a broken copy
  (a 900 px thread end, a 30 px Reply).
- `check_designs.mjs` on main's page with this mockup in `designData` and a two-option item (`answered` with `#pick-nested`,
  `re-row` with `#pick-rerow`): exit 0, `problem: null`.
- `label_once.py` on each state at 390: no hit.
- impeccable critique, in one context (no tool to start an agent): the detector found nothing. Fixed: the reply and its answer showed a bare
  time while "You asked" showed the day; both now show the day. Waited figures now use today's `waited` words ("under an hour").
  The Re: link is now 44 px tall, measured (about 42 by its CSS before).

## 10. Work outside this folder (for the builder)

- page.html: Reply, the reply box, threads in `askAll` and `renderAskList`, `.myreply`, `.fwait`, the reply draft key, `where` in the sent slot.
- skill `waiting-page`, "The database" and "Route an ask": the `re` field. The page writes it once at Send. The writer routes a reply to the
  `owner` of the record `re` names, or takes it when that session is gone.
