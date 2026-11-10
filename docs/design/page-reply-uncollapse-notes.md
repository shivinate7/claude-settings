# Waiting page, lane page-reply-uncollapse: design notes

Mockup: `docs/design/page-reply-uncollapse.html`. Screen: `skills/waiting-page/page.html` (main 21d20281).
Deep links: `#s=page|live|change|status|today|plain-list|reply-sorts-new|mark-words|live-mark-only|done-stays-folded`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. `#s=today` draws main for comparison.
Sizes: phone 390, mid 800 and wide 1280, light and dark. `layout.py devices` prints `unknown` for this repo, so the
sizes come from page.html's breakpoints at 520 and 960 and the Status tab's container queries at 464 and 640.
The mockup draws with page.html's own `<style>` (lines 8 to 840 at 21d20281). Each new rule reads a page token.
Options are named by name, never by a letter.

Settled by the brief and the coordinator (Nov 6), not options here:
- An item is new when the writer's `replied` (an ISO time) is later than both the owner's last Send (`freezeSeen`'s `last`)
  and `waiting.visit`. The writer sets `replied` only on a `reply` write or a `waits` change, never on `lastAnswer` alone.
- A roadmap step is new when `updatedAt` is later than the viewer's last visit.
- A reopened card unfolds in place and never re-sorts on the open page (ux-order-holds-still).
- A draft, a stood pick or a pending withdraw locks the fold open (`foldLocked`). A saved item never locks.
- An item the owner still owes never folds. A card folds only once it is answered.

## 1. An owed card never folds. Owner grant: yes

- What: a seen card (`isSeen`, no saved answer) draws its options or steps, ready line, None of these, Mark
  done and note box open, as a new card does. No `unfold` control on it. Only a sunk card (`isSunk`) folds.
  Drawn on No. 22, No. 20 and No. 24 in `#s=page`; main's fold in `#s=today`.
- Gain: each owed item is one press shorter. A reply that asks a new question shows its options at once, so a
  seen card needs no "reopen". Loss: the page is longer by each seen card's answer parts (measured: No. 20,
  a two-option decision at 390, 581px open against a 48px fold control).
- Departs from: SKILL.md lines 55 to 57 ("A seen card folds every answer part behind one control ... under a
  divider that reads Asked before"); stale-asks-sink-notes points 3, 4 and 5 (the fold, what it holds, the lock
  on a seen card); page.html `buildCard` (`const fold = isSeen(it) || sunk ? [] : null` becomes `sunk ? [] : null`),
  and the seen branch of `foldEls` and `unfoldBtn`. The sunk branch, the `foldLocked` lock and the words stay.
- Pick: keep the "Asked before" divider, the new-first order and the quiet seen ground (stale-asks-sink 1A, 2A).
  Why: they cost no press and still say what came since the last Send. The divider's words stay true.
- Option "Plain list" (`#s=plain-list`): no divider, no quiet ground; the order stays new-first. Gain: one
  look for every owed card. Loss: nothing on the page says which items are new since the last Send.

## 2. The new mark

- What: one mark, extended from the asks' `.newmark` home (page.html line 801): a pill with a filled dot, the
  accent ink `--acc` on `--acc-soft`, 1.5px `--acc` edge. Asks' "New answer" takes the same look.
  Item: it sits right after `No. <n>` in the top row. Step: in the row's `.meta`, after the tags.
- Words, and the accessible text:
  - Item: visible "New reply", hidden tail " since your last Send". Accessible text: "New reply since your last Send".
  - Step: visible "Updated", hidden tail " since your last visit". The `.rrow` button has its own `aria-label`,
    so the mark is `aria-hidden` and the label gains ". Updated since your last visit".
  - Phase rail and done fold: a count pill ("2"), `aria-hidden`; the button's label or a `.sr` span gains
    ", 2 updated since your last visit".
- Each later mark on a screen is the dot alone (`.newmark.dot`, 34px wide, so it never reads as a radio
  button), its words in a `.sr` span and in `title`. As the seen divider does (stale-asks-sink 1A, ux-label-once).
- Gain: green stays one meaning on the page (answered: `.ans`, `.card.answered`, `.tag.landed`), and the mark
  differs from the answered pill beside it on a sunk card. Loss: the asks' mark changes colour.
- Departs from: the asks' green "New answer" mark (page-ask-box-notes, ask-reply-back-notes). Owner grant: yes.
- Option "Words on every mark" (`#s=mark-words`). Gain: no shape to learn. Loss: `label_once.py` flags each
  repeat of "New reply".
- The mark is not colour alone: the dot and the edge are shapes, the words are text. `--acc` passes 4.5:1 on
  `--acc-soft` (waiting-page-notes point 1). In forced colours the edge and the dot stay (border, currentColor).

## 3. A sunk card with a new reply reopens

- What: an answered card in the Answered section whose `replied` is after the last Send opens its fold at load
  ("Hide your note, your last answer and the reply") and carries the mark (No. 18 in `#s=page`). It stays in
  the section, in its place. Neighbours No. 15 (reply before the Send) and No. 12 (no reply) stay folded.
- Builder: at load, set `state.unfold[id] = true` for each such card, once, beside `freezeSunk`. A press after
  that wins for the rest of the visit.
- Departs from: answered-sink-notes point 2 (every sunk card folds on load).
- A seen card with a new reply (No. 22) needs no reopen under point 1; it gets the mark only.
- Option "New reply sorts with new cards" (`#s=reply-sorts-new`): at load only, a seen item with a new reply
  counts as new and sits above the divider. Gain: position says new too. Loss: `freezeSeen` reads `replied` as
  well as `added`; the item jumps between loads. Pick: it keeps its place.

## 4. A reply that arrives while the page is open

- Pick (`#s=live`): the card unfolds in place and takes the mark; nothing re-sorts (No. 15, reply at 12:51).
  Content below it moves down. Today a pushed reply already grows a card's thread, so this is not new
  (ux-press-moves-nothing covers presses). Unless the owner pressed that card's fold this visit.
- Option "Mark only until next load" (`#s=live-mark-only`). Gain: nothing moves under the reader. Loss: the
  reply hides until a press or a reload.

## 5. Change on a reopened card

- `#s=change`: Change on No. 18 makes the open card with the old answer as a draft. The fold is locked open
  ("Stays open: your answer is ready"), as today. The mark stays for the visit.

## 6. How the item mark clears

- The new set is worked out once at load, like `freezeSeen`, from the same last-Send time. A Send on the open
  page changes no mark. At the first load after a Send, every `replied` before that Send is old: the mark goes
  and the sunk card folds again.
- Loss: the baseline moves only with a Send. With nothing owed, no Send comes, so a reopened card stays open
  and marked on every load. A press to fold it is page memory and does not last a reload. See Input Needed.

## 7. Roadmap steps

- What (`#s=status`): a step whose `updatedAt` is after the last visit draws open (`li.open`, the row's
  `aria-expanded="true"`) and carries the "Updated" mark (r22). Other rows stay folded (r21, r23, r24).
- The phase rail gives each phase with updated steps a count pill (Page upkeep 2, Later 1). It sits with the
  done count, away from the `.here` current-phase dot. Gain: a step in a phase not shown is not missed.
- A done step updated since the last visit (r19): the done fold opens, and the step is at its top, open and
  marked (`doneList` sorts newest `updatedAt` first). Option "Done fold stays folded" (`#s=done-stays-folded`):
  the fold head shows the count pill only. Gain: the box stays short. Loss: a step that just finished is one
  press away.
- Baseline: `waiting.visit`, one key for items and steps, read and written through the same stamp helper as
  `waiting.askSeen` (page.html `readStamp`, `writeStamp`). Read once at load, then written, so a mark lasts the
  load and clears on the next one; a reload counts as a visit. With no key (first visit, or storage blocked), no
  step is marked, and items use the last Send alone.
- Not changed: `fresh()` ("updated today", the feed's time words). It is another meaning; the mark does not
  replace it. Gap, not drawn: the owner sees a marked step on another pager page after paging there.
- Rail chips on the Questions tab: no mark. The chip has states (open, ready, sent); a fourth look is noise.

## 8. Outside this folder, for the builder

- `replied` is not in page.html's `itemFields` (line 901) or the SKILL.md item schema. Until it is, an item
  that carries it shows "This item carries a field the page does not draw."
- SKILL.md lines 55 to 57 need rewriting for point 1, and the item schema for `replied`.

## Checked

- Playwright, Chromium: all 10 states at 390, 800 and 1280, light and dark (60 runs). No script error, no
  sideways scroll. In a frame (picture mode), the focus ids `tier-holds`, `item-15` and `p-p2` each find a box.
- `label_once.py` on 5 states at 390: "Asked before" twice (the divider's `.sr` words, as today); "New reply"
  twice only in the option "Words on every mark"; Status, Why, When, Note, Done and To do on the Status tab
  (today's open-row labels, now with two rows open).
- impeccable detector: no finding. It reads the page markup only, not the screen in the script.
