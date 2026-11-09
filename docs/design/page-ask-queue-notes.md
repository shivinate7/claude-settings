# Waiting page Ask box, several asks: Stack, then send (design notes)

Mockup: `docs/design/page-ask-queue.html`. Screen: `skills/waiting-page/page.html` at 0dbab787. Its CSS (lines 8–774) is
copied whole into the mockup. Only `#newcss` is new.
Deep links: `#s=empty|one|several|edit|removed|send|sent|untold|reach|stale|failed|undone`, `&w=all|390|800|1280`,
`&t=light|dark`, `&lab=off`, `&hide=stale,copy`.
Sizes: phone 390 and desktop 1280, as the brief names. `w=800` draws page.html's mid band too. `layout.py devices` prints
`unknown` for this repo. Themes: light and dark.
Ruling: owner, waiting-page item 218 ("How should several asks queue on the waiting page?"), pick b, "Stack, then send",
2026-11-03 22:20 CST. "Asks stack in the box and go together on a final Send."
Owner report, Nov 2 12:55 CST: "can add only one ask before Send". Cause: `askState.sent` is one slot, and a second
`sendAsk` inside the 8 s window ended the first ask's Undo.

## 1. Add to list stacks an ask in the box

- States `one`, `several`. Add to list moves the typed words out of the box into "Not sent yet", under the buttons. It writes
  nothing to the store. Each stacked ask has a number in typed order, its words, Edit and Remove.
- The stack sits under the buttons, so a press moves neither the box nor its buttons. Only the list under the form moves down.
- A dashed edge marks an ask that is not in the store. The page uses dashed edges for "not yet" (`.btn.askgo:disabled`, `.unfold`).
- The rail and the Ask count pill count saved asks only (`askWaiting`). A stacked ask is not counted.
- Add to list checks `ASK_MAX` (4000) as Send ask does today. Over the limit, it stacks nothing and the hint says the length.
- Gain: the owner sees the whole batch before it goes. Loss: one more button beside Send.
- Departs from: `sendAsk`, one ask per press. Not blocking.

## 2. Send takes the list and the box

- State `several`. Send sends every stacked ask, plus the typed box if it holds text. The label counts both: "Send ask" for one,
  "Send 4 asks" for four. The hint says "Send takes the 3 in the list and the one in the box."
- With nothing stacked, type then Send is today's one-press send.
- The button keeps the box of "Send 99 asks" (a hidden sizer), so a new count never resizes it. Measured: 138 px at every state and size.
- Other option: Send takes the list only, and typed words need Add first. Gain: no doubt what goes. Loss: a single ask takes two presses.
- Pick: list and box.
- Departs from: the label "Send ask" (page.html `#askSend`), which never counts. Not blocking.

## 3. Ctrl+Enter sends

- Ctrl+Enter in the Ask section runs Send, as it does today (the keydown handler, "Ctrl or Cmd+Enter sends"). The hint keeps "Ctrl+Enter sends."
- Other option: Ctrl+Enter adds to the list. Gain: fast stacking. Loss: the hint's words and the key change meaning.
- Pick: keep it. An early send has Undo.

## 4. Edit and Remove a stacked ask

- Edit (state `edit`) opens the ask in place, in a textarea, with Done. It keeps its number and its place. Rows above do not move.
  The box keeps what is typed in it.
- Remove (state `removed`) keeps the row's place: "Removed: <words>" with Undo remove. The row goes at the next
  Add, Send or reload.
- Other option for Edit: move the words back to the box. Loss: it clashes with words already in the box.
- Pick: in place.

## 5. The stack is kept

- The stack is kept in `localStorage` `waiting.askStack`, beside `waiting.askDraft` (ux-keep-what-was-made). A reload shows it again under "Not sent yet".
- This cuts the ruling's loss "nothing reaches the writer until the final Send": a stack the owner left is still on view.
- Departs from: `saveAskDraft`, which keeps the box only. Not blocking.
- A browser that refuses the write, while the list has rows: the hint says "This browser would not keep your list, so a reload
  would lose it. Send it, or copy it and paste it in chat." Copy ask shows in the slot. An empty list has nothing to lose, so the hint goes with it.
- Departs from: `saveAskDraft`, which drops a refused write with no word. Not blocking.

## 6. Final Send

- State `send`. `canTell` runs once, then one write per ask. Each row shows "Saving…" or "Saved". Send is off while the batch
  saves, as `s.busy` does today. The box and Add to list stay on, so the owner can type the next ask.
- While the batch saves, the list's head reads "Sending", and the Send label counts only the box, so no ask is counted twice.
- Every record of the batch gets the same `at`, as `sendAll` gives one `at` to each answer. So one clock serves the Undo
  (`undoLeft`), and a session's 10 s wait holds for each record.
- One comment per Send, after the writes: "Asked on the waiting page. Writer: <writer>. 3 asks: <id>: <text>; …".
  Each text is cut at `ASK_NOTICE` (500). The whole comment is cut at `MAX_BYTES` (4096), as `noticeText` does.
- Departs from: `sendAsk`, one `canTell`, one write and one comment per ask. Not blocking.

## 7. One Undo for the batch, at the box

- State `sent`. The line under the buttons says "Sent 17:42. 3 asks." with today's `TOLD` or `NOT_TOLD` words, and
  "Undo send (7)" at its right end. One Undo takes back every ask of the batch. Its window is `UNDO_S` (8 s), read from the clock.
- The line sits where the stack was. The press and its answer stay in one place (ux-answer-at-press).
- When the count ends, the Undo keeps its box, hidden, until the line goes (ux-press-moves-nothing). The line goes when the owner types, as `s.sent` does today.
- Undo (state `undone`) deletes each record of the batch and puts the asks back in the list, in their order, ahead of any ask stacked
  since. The box keeps what was typed. The line says "Undone. Your 3 asks are back in the list, not sent." One comment:
  "Undone on the waiting page. Asks <ids> are withdrawn."
- While Undo's deletes run, the line says "Taking back 3 asks…", and the Undo has the look it has after the count: hidden, with no count.
- A delete that fails or comes after the window: the line names the code and the asks that stay sent, with the words `undoSend` uses for answers.
- Focus: when the Undo button goes hidden (a press by click or Enter, the count's end, a failed Undo) while it has focus,
  focus moves to the ask box first, so it never falls to the body.
- Copy answers shown: at 520 px and under, the bar status takes its own row. At 800 and 1280 it stays inline with the buttons.
- Departs from: `renderAskForm` and `askSlot`, which put the Undo in the hint row's slot, and `undoAsk`, which puts the words back in the box.
  The slot now holds only Copy ask when the store cannot be reached. Not blocking.
- Departs from: `renderAskForm`, which drops the Undo button when the count ends. Not blocking.
- Item 5 of `page-ask-box-notes.md` now cites this ruling.
- A second Send while the Undo counts: Send stays off until the count ends, and until an Undo whose delete is still awaited is done.
  The hint says so with no seconds, so the live region does not speak at each tick: "Send turns on when the Undo count ends."
  Once the window has passed while a delete still runs, it says "Send turns on when Undo is done."
  An Undo that runs inside the window says the same: the count is no longer what Send waits for.
  With an ask not saved, it says "Send ask tries the one not saved again when the Undo count ends." Add to list stays on with words in the box,
  so the owner stacks the next asks meanwhile, and the hint says so only then. With the box empty, Add is off and the hint does not name it.
- Undo puts each ask in the kept list before its delete, and reads the window before each delete. A window that ends between two deletes
  leaves the later asks sent, and the line says "Too late to undo 2 asks. They stay sent." Focus goes to the ask box, as after "Undone".
  - Gain: no Undo is cut short. This was the cause of the Nov 2 report. Loss: the next Send can wait up to 8 s.
  - Other option: the new batch ends the old Undo, and the line says so. Loss: an Undo the owner may need is gone.
  - Other option: one Undo for both batches. Loss: the first batch's window would pass the 10 s a session waits.
  - Pick: Send stays off. Not drawn.
  - Departs from: `sendAsk`, which takes a second send and ends the first Undo (`clearInterval(askTimer)`). Not blocking.
  - Departs from: `undoAsk`, which reads the window once, at the press, and has no late line. Not blocking.

## 8. Each ask's reach after send

- States `sent`, `untold`, `reach`. Each sent ask is its own row in the list, newest first, with today's words from `askItem`:
  "Waiting for <writer> to read it.", "Read by <owner> <time>. Waiting for its answer.", or the answer thread.
- A routed ask shows its new owner ("Read by lane hooks-batch"). An answered one opens with "New answer", as today.
- The told or untold fact is one fact for the batch, so it shows once, on the line at the box, and not on each row (ux-label-once).
- Open for the builder: in one batch the rows share `at`, so the id breaks the tie (`askAll`). The ids must sort so the last-typed ask is on top.

## 9. One ask not saved

- State `failed`. Each write is tried. A write that fails leaves its ask in the list, with a `--due` edge, its words, and
  "Not saved (permission-denied). Your words are kept here." (`role="alert"`). It gets Copy ask, Edit and Remove.
- The saved asks go to the list. The line says "2 of 3 sent 17:42." with the told words. Undo covers the two that saved.
- Send ask, now counting 1, tries it again. No second Try again control, so the act keeps one name.
- When every write fails, the line says "Not saved (<code>). Your 3 asks are kept in the list: copy them and paste them in chat.",
  and Copy ask shows in the slot. Not drawn.
- Other option: stop at the first failure, as `sendAll` does, and leave the rest unsent. Gain: same rule as answers. Loss: one
  bad write holds back asks that would save. Asks do not depend on each other.
- Pick: try each.
- Kept: the code in brackets, as `renderAskForm` shows it today.
- Departs from: `renderAskForm`'s failed hint, which keeps the words in the box. Not blocking.

## 10. Empty box

- State `empty`. Add to list and Send ask are off, with today's dashed look. The hint says why, in the words of today's hint for Send ask (`renderAskForm`), with Add to list added.
- At 390 the hint row keeps three lines (66 px), so a change of hint never moves the buttons under it. Measured: every drawn hint fits.
- Departs from: the hint "Send ask turns on once you type." Not blocking.

## 11. The not-read line (hide: "the not-read line"). Owner grant: yes

- State `stale`. Kept from the explore notes; item 218 did not answer it. An ask with no `read` after 15 minutes says
  "Not read by triage after 40 minutes. If triage is not running, copy the ask into a session's chat."
- The 15 minutes are unmeasured. They are a pick for the owner to change.
- Gain: a stuck ask says it is stuck, and how to go on. Loss: one more line to keep true, on each row of a stuck batch.

## 12. Copy ask on a stuck row (hide: "Copy ask on a stuck row"). Owner grant: yes

- Kept from the explore notes; item 218 did not answer it. A row with the not-read line gets Copy ask. It copies that row's words (`copyText`).
- Gain: the row leads on (ux-no-dead-end). Loss: one more button per stuck row.

## 13. What the page cannot know

- `askWriter()` reads `meta/page.writer`. After a triage rotation that name can be stale.
- No state claims "delivered" or "woke". Only `read` confirms a read.

## 14. Measured verdicts

Headless Chrome, every state at 390, 800 and 1280, in light and dark. Checks: no sideways scroll, no element past the
page edge, and every Ask button at least 44 px high. Also: the 390 hint at 66 px or less, and one Send box size at every state.
The edge and button checks went red on a broken copy, with a 900 px box and 30 px stack buttons.

| State | 390 | 800 | 1280 |
|---|---|---|---|
| all 12 states, light and dark | pass | pass | pass |

## 15. Work outside this folder (for the builder)

- page.html: `askState.stack` (kept in `waiting.askStack`), Add to list, a batch send with one `at`, one comment and one Undo,
  the line under the buttons, the failed row, and the Send label count.
- SKILL.md: the writer reads several asks with one `at`. No change to the record fields.
