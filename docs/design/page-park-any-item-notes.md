# Waiting page, step page-park-any-item: design notes

Mockup: `docs/design/page-park-any-item.html`. Screen: `skills/waiting-page/page.html` (main 0497265b): `buildCard` (the `.alts` row), `readyText`, `receipt`, `lastAnswerEl`, `renderBar`, `answerLine`, and the parked-line code (`pressPark`, `ACT_NAME`, `pkLine`, `parkedEl`).
Deep links: `#s=today|open|park|stood-park|task-park|sent|answered|moved|back|seen|blocked|ruling|copy|hint-ready|seen-out|ruling-park|count-plain|copy-word`,
`&w=all|390|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Sizes: phone 390 and wide 1280. Themes: light and dark.
Focus ids: `#b-park-<item id>` (in the mockup: `#b-park-rail-count`, `#b-park-duo-sim`, `#b-park-chip-colour`), `#rc-rail-count` (the receipt), `#pk-line-rail-count` (the moved line).
Focus per choice: cards and wording `#b-park-rail-count`; the hint `#rd-rail-count` (`#s=park` against `#s=hint-ready`); the seen card `#unfold-rail-count` (`#s=seen` against `#s=seen-out`); rulings `#ralts-rule-7` (`#s=ruling` against `#s=ruling-park`); counts `#barStatus`; copy text `#copyBox`.
The page CSS in the mockup is page.html's own style block at 0497265b. This step adds no CSS. Where the mockup and page.html differ, page.html and these notes win.
The fixed contract is unchanged.

Departs from: `skills/waiting-page/page.html:buildCard`. Each open decision and task card gets Park in `.alts`. Today only the writer can park an item.
Departs from: `skills/waiting-page/SKILL.md` "The database". `answers/<id>` gains the park shape `{item, n, at, act: "park", note}`.
Departs from: `skills/waiting-page/SKILL.md` "Route and close". A new branch for `act: "park"` (item 7).

## 1. Which cards get Park

- Open decision and task cards (pick, `#s=open`): Park sits after None of these or after Mark done. This covers a card in the Answered section after Change. It also covers each member of a group, and Park parks that member only. Gain: the owner can park any question, as asked. Loss: parking one member of a group splits the bundle, and the other members stay under the group title.
- Seen card, Park inside the fold (pick, `#s=seen`): Park sits in `.alts` with None of these, behind "Show the N options". The mockup draws the fold open. Gain: one home for the control. A park draft locks the fold open through `foldLocked` (`!!eff(it)`), and the fold is already open when the owner presses Park, so nothing moves. Loss: one more press on a seen card.
- Option "Park beside the fold control" (`#s=seen-out`): Park sits outside the fold. Gain: one press. Loss: `foldLocked` opens the fold on the press, and all content below it moves (`ux-press-moves-nothing`). Avoiding that needs a second rule that exempts a park draft from the lock. It also gives the control a second home.
- Ruling cards: no Park (pick, `#s=ruling`). Option "Park on a ruling" (`#s=ruling-park`). Loss: `savedOf` keeps a ruling's record only when `choice === OVERTURN`, so a park record would draw no receipt and count as no answer. A ruling already stands with no act, so a park would change nothing the owner sees.
- Blocked cards (pick, `#s=blocked`): Park is disabled with None of these and Mark done (add `.parkbtn` to the `blocked(it)` selector in `buildCard`). The status alert above the options gives the reason, and the ready line says "This item cannot be sent." Gain: same as today's controls. `answerBody` writes `n`, and a blocked card can lack `n`. Loss: a broken item cannot be parked from the page. The owner pastes "park <n>" in chat, as in the step's interim.

## 2. Wording and hint

- "Park", with no hint on the card (pick). The ready line reads "Ready to send: park." The owner sees where the item goes in two steps: the receipt "Parked.", then the line in "Parked by you" with Unpark. Gain: one short word, and the same word as the "Parked by you" block (`ux-one-plain-name`). Loss: on the first use, the owner learns where the item went only after the writer moves it.
- Option "Hint in the ready line" (`#s=hint-ready`): "Ready to send: park. It moves to Parked by you." Loss: `.ready` is `nowrap` with an ellipsis, so at 390 the hint is cut. A wrapping ready line changes the card's height on a press.
- The button's visible name is "Park" only, as in the contract. Its card's `aria-labelledby` names the item. The note label stays "Note to the session (optional)", and its text is sent as the parked note.

## 3. Counts in the Send bar and the rail

- A park counts as an answer (pick, `#s=park`):
  - Bar: "2 ready (1 where my pick stands, 1 to park). 1 stays open." "to park" sits in the brackets with "overturn". It differs from "on parked lines", which counts Unpark and Drop, so each act keeps one name.
  - Send: "Send 2 answers".
  - Rail: the chip turns ready, and "N ready to send" counts the park.
  - "of N sent" counts a sent park until the writer closes the item. Then the total drops.
  - A staged park leaves "N stay open". `renderBar` does this today, because `pks` counts only parked-line pseudo items.
  - Gain: one count rule for every answer. Loss: "sent" counts a deferred item for a short while.
- Option "Bar without a park count" (`#s=count-plain`): "2 ready. 1 stays open." Gain: shorter. Loss: the bar no longer says that Send parks an item.

## 4. Chat copy text (no store)

- "3 park (Wait until the batch merges.)" (pick, `#s=copy`). It uses the `answerLine` grammar `<n> <choice>`, as "4 done" does, so triage reads one grammar. Loss: the step's interim reads "park <n>". Triage reads by number, so both forms parse.
- Option "Copy as Park No. n" (`#s=copy-word`): "Park No. 3 (...)". Gain: it reads as a sentence. Loss: a second grammar on the same line.

## 5. The press

- Park is `.btn.dash` with `aria-pressed`, as None of these is. Pressed, only its edge turns from dashed to solid. There is no ✓ label, because None of these and Mark done have none.
- Measured in headless Chrome at 390 and 1280, in `open`, `park`, `stood-park` and `task-park`: each `.alts` row is one 44px row. Each button keeps its place and size, and each card keeps its height. A press moves nothing.
- Stood pick, then Park (`#s=stood-park`): the pick is unselected, the gold "my pick" box stays as text, and the ready line reads "Ready to send: park." The bar's stood count drops by one. A second press clears Park, and the stood pick stands again, as before the press. Park does not set `unstood`. This is no contract change. It makes one reading of the contract explicit for the test-author.

## 6. After Send

- Sent (`#s=sent`): the card keeps its place. It shows the receipt "Parked." with Change, and the note line under it. The Sent panel lists "No. 3", as today. Undo is as today.
- Next visit (`#s=answered`): the card is in Answered. It shows "Parked." with Change, and "Show your note" folds the note.
- Change stages Park again with the saved note, as `{act: "park", note}`.

## 7. The writer moves it (`#s=moved`)

Owner grant: yes (a SKILL.md "Route and close" change; a builder places it).

- For an answer with `act: "park"`, the writer adds a `meta/page.parked` entry `{id, ref, note}` in one update pinned with `if_version`. Then it closes the item and deletes `answers/<id>`.
- `id` is the item's id when it matches `PARK_ID` (`^[a-z0-9-]{1,32}$`) and is unique in the list. Otherwise the writer gives a new slug. A line with a bad id draws with both acts off.
- `ref` is the item's home and title, in plain words. `note` is the owner's note.
- A parked line with no note draws its ref with no colon (pick; a `pkLine` change). Option: the writer writes "No note." Loss: the page then shows words that the owner did not write.

## 8. Unpark brings it back (`#s=back`)

Owner grant: yes (a SKILL.md change: `lastAnswer` may hold `act: "park"`).

- The writer adds the item again with a new number and `lastAnswer: {act: "park", note, at}`. `lastAnswerEl` shows "Parked." and the note (pick). Gain: the owner sees why the item was set aside. Option: no last answer. Loss: the note is lost.

## 9. For the builder

- `setDraft`: keep a draft that holds only `act`. Today it deletes it.
- `eff`: return a draft with `act: "park"` as it is, before the stood overlay. `readyText`: check the park act after `blocked` and before `d.stood`. `draftReady`: true for a park act on a card that is not blocked.
- `choose`, `toggle`, None of these and Mark done each clear `act`. Park clears `choice` and `done`, and keeps `note`.
- `signature()`: add `d.act`, so a press repaints the card.
- `answerBody`: `{item, n, at, act: "park", note}`, with no `choice` or `done`.
- `receipt()`: check `sv.act === "park"` first ("Parked."). Today a task would read "Not marked done" and a decision "You chose an option". Its Change handler copies `act`.
- `lastAnswerEl`: `la.act === "park"` reads "Parked."
- `renderBar`: count card parks as "N to park". `answerLine`: "<n> park (<note>)".
- `undoSend` puts back the saved draft as `w.draft`. Keep `act` in it, or an undone park comes back as "none of these, with your note" or "note, not done".
- `noticeText`: a park entry reads "<n> park (<note>)". Today an entry with no choice and no done reads "note, not done".
- Park inherits `.btn.dash`'s `--line` edge, which is under the 3:1 state-cue floor. None of these and Mark done have that gap today, and fixing it is outside this step.
