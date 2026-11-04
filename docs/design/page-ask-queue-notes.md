# Waiting page Ask box, step ask-reaches-writer: design notes

Mockup: `docs/design/page-ask-queue.html`. Screen: `skills/waiting-page/page.html` at 72034d9a. Its CSS (lines 8–773) is
copied whole into the mockup. Only `#newcss` is new.
Deep links: `#s=rows|saving|untold|stale|failed|boxrow|stack|bar`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`,
`&hide=rows,boxrow,stack,stale,copy`.
Sizes: 390, 800 and 1280, which are page.html's bands. `layout.py devices` prints `unknown` for this repo. Themes: light and dark.
Owner report, Nov 2 12:55 CST: an ask sent 11:55 still read "Waiting for home-triage-4 to read it." an hour later. Also,
"can add only one ask before Send".

## 1. What stops a second ask today (read, not measured)

- `askState.sent` is one slot. A second `sendAsk` inside the 8 s window sets a new `s.sent` and runs `clearInterval(askTimer)`.
  That ends the first ask's Undo. The guard `s.sent === sent` then drops the first ask's told status.
- `s.busy` turns Send ask off while `canTell` (up to `CAN_WAIT_MS`, 3 s) and the write run.
- The box itself takes a second ask once the first one saves. So the limit is the single Undo and status, not the box.

## 2. Question 1: how several asks queue. Owner grant: yes

- **Undo on each row (pick)**, state `rows`, focus `#askRows`. Each Send writes at once. The ask goes to the top of the list,
  with its own status line and its own `Undo send (n)` at the right end of that line. The hint row says
  "Sent 17:42. 2 asks can still be undone, each on its row below. Type the next one any time."
  - Gain: any number of asks, each with its own Undo. The new row sits directly under the box, so the answer stays next to the press (ux-answer-at-press).
  - Loss: Undo is no longer in the hint row.
- **Latest Undo at the box**, state `boxrow`, focus `#askBoxRow`. The hint row keeps the latest send and its Undo, as today.
  An earlier send that is still in its 8 s gets its Undo on its row.
  - Gain: the latest Undo stays where it is today. Loss: Undo has two homes, and the latest ask's status shows at the box and not on its row.
- **Stack, then send**, state `stack`, focus `#askStack`. "Add to list" stacks the typed ask under the box, with Remove.
  "Send 3 asks" sends them all. Then each row works as in the pick.
  - Gain: matches "add several before Send" word for word. Loss: a second button, and stacked asks that were never sent can be forgotten. A batch can also half fail.
- Departs from: `page-ask-box-notes.md` item 5, "The Undo shows at the box, in the hint row" (`renderAskForm`, `askSlot`). This applies to
  the pick and to Stack. Not blocking.
- Each option has its own Hide control.

## 3. Send clears the box at the press (pick)

- Each press runs its own `canTell`, then its write, keyed by the ask id. The box clears at the press, and the row says "Saving…" (state `saving`).
  Send ask turns on again as soon as the owner types.
- Gain: the owner can type the next ask while the last one saves. Loss: a write that fails needs the failed row (item 8).
- Departs from: `sendAsk`, which clears the box only after the write, and `s.busy`, which turns Send ask off meanwhile.
- Kept: `canTell` runs before the write, so the comment still follows the owner's own press (comment in page.html above `canTell`).

## 4. Status words: each claims only what the page knows

One home for the words, as `TOLD` and `NOT_TOLD` are today. Each status rests on one fact:

| Status | Fact | Words |
|---|---|---|
| saving | write running | "Saving…" |
| told | write done, and `notifyClaude` returned true | "Saved 17:42. A wake was sent. Not read by triage yet." |
| untold | write done, and `canTell` or the send was false | "Saved 17:42. No session was told. It waits for triage's next wake or turn start." |
| saved | record only: after a reload, or after the Undo count | "Saved 17:41. Not read by triage yet." |
| read | the record has `owner` and `read` | today's words: "Read by <owner> <time>. Waiting for its answer." |
| answered | the record has `reply` | today's thread, unchanged |

- "A wake was sent" is the comment send. It does not say that any session woke. Only `read` confirms a read.
- The told or untold fact is in memory only. After a reload the row falls back to "saved". That is true, and needs no new storage.
- "triage reads it at its next wake or turn start" is true by `SKILL.md`: "The writer also reads `asks/` at each wake and turn start".
- No row and no hint says "reply in the thread". `SKILL.md`, "Read the answers", forbids a session to reply in a comment thread.
- Departs from: `TOLD` ("Claude was told.") and `NOT_TOLD` (page.html, beside `MAX_BYTES`). This is a fix for ux-statements-are-true. No grant is needed.
- Gain: the Nov 2 ask would have said "Not read by home-triage-4 yet", plus its age. Loss: longer lines.

## 5. Undo per row

- Each row's count is read from the clock with `undoLeft(a)`, so `UNDO_S` (8 s) and the 10 s that a session waits stay as today. One interval ticks every open count.
- Undo deletes that ask only. It puts the words back in the box, ahead of what is typed, as `undoAsk` does today. It sends today's "Undone on the waiting page" notice.
- When a count ends in this view, its button keeps its box, hidden, until the next load. So no row below moves (ux-press-moves-nothing). See row 3 in `rows`.

## 6. The not-read line (hide: "the not-read line"). Owner grant: yes

- State `stale`. An ask with no `read` after 15 minutes says "Saved 17:02. Not read by triage after 40 minutes. If it is not running,
  copy the ask into a session's chat." The row's head keeps "waited 40 minutes" (`waited`).
- The 15 minutes are unmeasured. They are a pick for the owner to change.
- Gain: a stuck ask says it is stuck, and how to go on. Loss: one more line of words to keep true.

## 7. Copy ask on a row (hide: "Copy ask on a row"). Owner grant: yes

- An `untold` or `stale` row gets Copy ask. It uses `copyText`, as `copyAsk` does. It copies that row's words, not the box.
- Gain: the row has a control that leads on (ux-no-dead-end), and the control never says "reply in the thread". Loss: one more button per stuck row.

## 8. A row that is not saved

- State `failed`. The row keeps the owner's words and says "Not saved (permission-denied). Your words are kept here." It has Try again and Copy ask, and `role="alert"`.
  Its head says "Not sent, typed 17:42" with the due triangle, never "You asked" and the waiting disc, because nothing is in the store. The box keeps the next ask.
- Kept: the code in brackets, as `renderAskForm` shows it today. ux-machine-text-hidden would put it behind a disclosure. That is a wider change to every "Not saved" line, so it is not made here.
- Departs from: `renderAskForm`'s failed hint, which keeps the words in the box. With a queue, the box may already hold the next ask.

## 9. The answer bar shares the words

- `sendAll` reads the same `TOLD` and `NOT_TOLD` (`setSentStatus`). State `bar` draws them: "No session was told. Each owner reads its answer at its next wake or turn start."
- `sendAll`'s write failure `barNote` ends "Copy the answers and reply in the thread." New: "Copy the answers and paste them in chat." It is not drawn, and the builder changes it.

## 10. What the page cannot know

- `askWriter()` reads `meta/page.writer`. After a triage rotation that name can be stale, and the page cannot tell. The cause fix is in the
  skill (the new writer watches the page at start, step note), not on this screen.
- No state claims "delivered" or "woke". Only `read` confirms.

## 11. Measured verdicts

Headless Chrome, every state at 390, 800 and 1280, in light and dark. Checks: no sideways scroll, no element past the page edge,
and every Ask button at least 44 px high. Both checks went red on a broken copy, with 30 px row buttons 900 px wide.

| State | 390 | 800 | 1280 |
|---|---|---|---|
| rows, saving, untold, stale, failed, boxrow, stack, bar (light and dark) | pass | pass | pass |

## 12. Work outside this folder (for the builder)

- page.html: the ask state is keyed by id (`sent` becomes a map), with per-row status and Undo in `askItem`. Also the new words, and `barNote`.
- SKILL.md: no change for the words. The writer-watch fix is in the step note.
