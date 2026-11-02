# Waiting page Ask box, step page-ask-box: design notes

Mockup: `docs/design/page-ask-box.html`. Screen: `skills/waiting-page/page.html` (main ea92b0cc).
Deep links: `#s=a|empty|loading|sent|failed|offline|b|c`, `&w=all|390|800|1280`, `&t=light|dark`,
`&lab=off`, `&hide=a,b,c,rail,older`. Hide A also hides the five A states. The mockup uses page.html's own CSS, copied into it.
Sizes: phone 390, mid 800 and wide 1280. The brief names 390 and 1280; 800 is page.html's mid band.
`layout.py devices` gives no list for this repo.
Themes: light and dark. The settled defaults of the step note are not opened again.

## 1. Placement

- A (pick): one Ask section after both tab panels (`#qView`, `#sPanel`), above the answer bar.
  It ends the Questions tab and the Status tab. This is the bottom of the page, as the step note says.
  Gain: one home, and the owner can ask from either tab. Lose: on a long list the box is far down.
  Item 7 helps with that.
- B: a third tab, Ask, with a count of waiting asks. Gain: one press from the top. Lose: the box
  is out of view behind a tab. With Designs, a 320 phone has four tabs, and the row wraps.
- C: one line to type in the fixed answer bar, with the list at the page end. Gain: always in view.
  Lose: the bar has two Send buttons and grows to about 150px on a phone. It covers more of each card.
- Owner grant: no for A. B and C depart from the step note ("at the bottom"), so each one needs a grant.
- State and focus for a look item: A `a` and `#askA`, B `b` and `#askB`, C `c` and `#askC`.
- Pick: A.

## 2. Layout of the section

- On a wide screen the section keeps the list's grid: 240px, then the rest (page.html `.main`).
  The heading and one line of help sit in the rail's column. The box and the asks sit in the list's column.
- At 960 and narrower it is one column, as `.main` is.
- Heading: a half-filled disc, "Ask", and a count pill of waiting asks (the shape of `.tier > header .ct`).
- Gain: the box lines up with the cards above it. Lose: on a wide screen the left column holds only the heading.
- Pick: the two columns.

## 3. The record, `asks/<id>`

- Key: `ask-` plus `Date.now()` in base 36 plus two random characters. The `id` field equals the key, as for `items/`.
- The page writes `id`, `text` (the owner's words, line breaks kept, 4000 characters or fewer) and `at` (ISO).
  It writes them once, at Send. A text over 4000 characters is never cut: Send ask writes nothing, the words stay in the box,
  and the hint says the length and the limit. An Undo that brings the box over 4000 does the same.
- The writer and the owning session write only these fields:
  - `owner`: the session that has the ask. The writer sets itself, or the session it routes the ask to.
  - `read`: ISO time when `owner` read it.
  - `reply`: the answer, plain text, line breaks kept. A feedback ask also gets a short reply.
  - `answered`: ISO time of `reply`.
  - `home` and `filed`: where a feedback ask was filed, in plain words, and when.
- A session never writes `text` or `at`. ArtifactData writes as the owner, so this rule is the
  only thing that keeps the owner's words apart from a session's. It is the same as for `answers/` in SKILL.md, "Read the answers".
- The names reuse `owner`, `reply`, `read`, `filed` and `home` from `items/` and `receipts/`.
- An ask with `reply` is answered. An ask with no `reply` waits.
- Gain: one record per ask, and the page draws each state from it. Lose: only a written rule keeps a session off `text` and `at`.
- Pick: this shape. The step note settles one record for the ask and its answer.

## 4. An ask is never a grant

- An ask is never the owner's grant for an act. When an ask needs a grant, the writer adds an item for it.
- Gain: the grant stays in `answers/<id>`, the one place the guard and SKILL.md read.
- Lose: "please merge PR 12" typed in the box needs one more press.
- Owner grant: yes. This adds to the grant rules in SKILL.md, "Read the answers".

## 5. Send and Undo

- Send ask writes `asks/<id>`. Then it tells Claude with one comment, through `canTell` and
  `notifyClaude` (page.html), as `sendAll` does today.
  - Send notice: "Asked on the waiting page. Writer: <writer>. Ask <id>: <text, cut at 500 characters>."
  - Undo notice: "Undone on the waiting page. Ask <id> is withdrawn."
  - When no comment can go: today's `NOT_TOLD` words.
- Undo: 8 seconds (`UNDO_S`), read from the clock, as `undoLeft` does. Undo deletes `asks/<id>`
  and puts the text back in the box. A session waits 10 seconds after `at` before it reads, as for an answer.
- The Undo shows at the box, in the hint row beside Send ask (ux-answer-at-press). It does not use
  the `.sent` panel above the bar. That panel grows the fixed bar, and at 390 it would cover the box.
- Send answers and Send ask never mix. The bar's count ("1 ready") never counts an ask. The bar does not change in `#s=sent`.
- Send ask is off while the box is empty. The hint says so: "Send ask turns on once you type."
  Ctrl+Enter sends on a fine pointer. The hint drops those words on a touch screen.
- The typed text is kept in `localStorage` `waiting.askDraft`, as `waiting.draft` keeps a note (ux-keep-what-was-made).
- An ask cannot be changed after the Undo time. A follow-up is a new ask.
- Departs from: page.html `openSent` and `renderSent` — the Undo for an ask shows at the box, with no stamp. The window, the clock read and the notices stay as today.
- Gain: the answer to the press is at the press, and the box is never covered. Lose: two Undo places on one page.
- Pick: Undo at the box.

## 6. Waiting and answered states

- Waiting, not read: "Waiting for <writer> to read it." The writer's name comes from `meta/page`.
- Waiting, read: "Read by <owner> <time>. Waiting for its answer." These are the receipt words of today (`receipt`).
- Each waiting ask shows "waited <span>", as a card does (`waited`). A stuck ask shows its age.
- Answered: "Answer from <owner>, <time>", then the reply, in the `.thread` panel of today.
  A filed ask adds "Filed in <home>, <time>".
- Shapes: a half-filled disc for waiting, today's `.g.done` check for answered. The hollow ring
  already means Whenever, so it is not used (ux-one-plain-name).
- Gain: the owner sees who has each ask and how long it has waited. Lose: one more shape on the page.
- Pick: these states.

## 7. A rail link (hide control: "Hide the rail link")

- The rail gets an Ask row: the disc, "Ask" and the count of waiting asks. It jumps to the section.
  With no asks it is grey, as an empty tier is. With asks not read it shows "—".
- Gain: on a phone the rail is at the top, so the box is one press away. Lose: one more rail row.
- Pick: keep it.

## 8. Fold

- An answered ask folds to one row: the check, the ask (one line, two on a phone), "Answered <time>" and "Show answer".
  The whole row is one button, 48px tall.
- An answer stays open while it is new to this viewer. It shows "New answer".
  The page keeps a seen mark per viewer in `localStorage` `waiting.askSeen`, an ISO time, set when the page is hidden.
  When storage fails, answers from the last 24 hours stay open and older ones fold.
- A fold happens only at a page load or at a press. A row never folds while the owner looks at it.
- Fold and Show answer sit at the same spot, the right end of the first line. Focus goes to the control at that spot after a press.
- Order: newest first by `at`. A reply never moves a row (ux-order-holds-still).
  A new ask goes in at the top of the list, under the box. The box and all above it stay still.
  The rows under it move down one row. That is the cost of "newest first" in the step note.
- The other lane folds options behind `button.unfold`. I did not see its code. The control here
  uses the look of `.morebtn` and the class `unfold`. The lane that lands second matches the class.
- Gain: the list stays short, and a new answer is not missed. Lose: an older answer needs a press to read.
- Pick: fold, with new answers open.

## 9. Older asks (hide control: "Hide older asks")

- The list shows each waiting ask, each new answer (whatever its age) and the newest 3 answers already seen. "Show N older asks" shows the rest.
- No step in the note removes an ask, so without a cap the page grows with no end.
- Owner grant: yes. Does the writer ever delete an answered ask, and after how long? Pick: never.
  The page caps what it shows.

## 10. Empty, loading and failed states

- Nothing asked: "Nothing asked yet. Type above, and a session answers here." The box above is the one control.
- Loading: "Loading your asks…". The box works before the list loads (ux-unknown-is-not-empty).
- Write failed: "Not saved (<code>). Your ask is still in the box: copy it and paste it in chat."
  A Copy ask button shows beside Send ask, as "Copy answers" does today. Send ask stays on, so the owner can try again.
- Store not reachable (`state.db === false`): Send ask is off, and the hint says why. Copy ask shows.
  The list says "Your asks cannot be read in this view." It never says "nothing asked".
- Gain: each state has its own words, and no typed text is lost. Lose: four more strings to keep true.
- Pick: these four states.

## 11. Send ask when off

- Off, Send ask keeps its box and label, with a dashed edge and muted text. The look is that of
  `.btn.mv[aria-disabled]`.
- Departs from: page.html `.btn:disabled`, opacity .45. At that opacity the label of Send ask nearly vanished in both themes.
- Gain: the owner sees the control and the hint that says why. Lose: two off looks on one page.
- Pick: the dashed look for Send ask only. Owner grant: no.

## 12. A phone with the keyboard up

- The fixed bar stays. Today's `scroll-padding-bottom` (96px) keeps a focused box above it.
- Unmeasured: a real phone with the keyboard up. The builder checks it on a 390 device.
- Gain: no new behaviour. Lose: if the bar covers the box with the keyboard up, a later fix hides the bar while the box has focus.
- Pick: keep the bar.

## 13. Ship together or apart

- Apart. The Ask section has its own render function, its own database listener and its own
  state. It does not change `renderList`, the tiers or the cards. The two lanes share only the look of a fold control.
- Item 7 adds one row at the end of `renderRail`. The tier lane may also change that function. That is a text conflict at merge, not a clash of behaviour.

## 14. Work outside this folder (for the builder)

- SKILL.md, "The database": the `asks/<id>` fields and the rule in item 3.
- SKILL.md, "Read the answers" and "Route and close": the writer lists `asks` at each wake. It takes or routes each
  ask with no `owner`. It files feedback as a chat message (`local_time.py --page-note`). It never writes `text` or `at`.
- A guard: an allow list of the session fields of item 3, read from one constant in page.html, as `itemFields` is.
- page.html: the section, its listener on `asks`, the draft and seen keys, and the rail row.
