# Waiting page, lane answered-leaves-page: design notes

Mockup: `docs/design/answered-lane-no-row.html`. Screen: `skills/waiting-page/page.html` at 6e8d6ccf9 (page.html last changed in fc54573e8).
Deep links: `#s=before|after|filing|both`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=after,filing`.
Sizes: phone 390, mid 800, wide 1280, light and dark. `layout.py devices` prints `unknown` for this repo, so the sizes come
from the brief. The screen CSS is page.html's own `<style>` (lines 8 to 914 at 6e8d6ccf9), copied whole. The mockup adds no
screen CSS; only the harness and the dashed sample labels have their own.

The sample: the page loaded Nov 10 at 09:00 CST. No. 63 carries `lane` (glossary-pass) and `lastAnswer` (sent 08:48) and has
no answers row. No. 23 is open. Answered already holds No. 58 (lane and a wait), No. 52 (a kept answer with `lane`) and No. 44
(waits on a PR).

The ruling: owner, page item 477 (Nov 10, 09:06 CST). An answered item whose grant is relayed stays open but leaves the
questions area. It stays open, so page_grant.py reads it unchanged.

## 1. No. 63 sinks into Answered at load

- What: an item with `lane` and `lastAnswer` and no answers row (`isSaved` false, `isByWait` false) sinks at load, folded,
  as an answered-by-wait card does. States `before` (today: open in Blocking) and `after`.
- Gain: the questions tiers hold only questions the owner has not answered. The Blocking count, the Questions tab count and
  the bar's "N stay open" drop by one.
- Loss: none seen. A Change still reopens the card in place in Answered, as on any sunk card.
- Pick: sink. Owner grant: item 477 (Nov 10, 09:06 CST).
- Departs from: `lane-answered-sink-notes.md`, "Settled", first line: "A lane item sinks only when its answers record
  exists (`isSaved`) ... No lane + `lastAnswer` predicate (coordinator, Nov 6 15:47 CST)." Item 477 overrides it.
- Built: one home. Widen `answeredByWait` (page.html line 1234) to an "answered off the page" predicate:
  (`waitsOf(it)` or `laneOf(it)`) and `lastOf(it)`. Every reader of it then takes the item with no other change:
  - `freezeSunk` (line 1187): the item joins the sunk set at load.
  - the seen rule in `freezeSeen` (line 1174): it never counts as an old open item.
  - `isByWait` (line 1236), so `isAnswered`: the tier count (line 1990), the rail's open counts (line 2082), "N of M sent"
    (line 2062), `qCount` (line 3001), the bar's open count (line 2096) and `staged`.
  - `sentOf` (line 1239): the item's place in Answered.
  - `buildCard` (line 1683): `byWait` is true, so the card draws as sunk and folded, not as an open card in Answered.
- Must also change: the chip's aria-label (line 2068) calls `waitWords(waitsOf(it))`. With a lane and no wait, `waitsOf` is
  null and this throws. Give it a lane branch: ", answered, waits on lane <slug>". The name `isByWait` then reads wrong;
  the builder may rename it, which is a code choice.

## 2. The pill: "Sent <lastAnswer.at>"

- What: the folded card's pill. There is no answers row, so its time is `lastAnswer.at`.
- Option "Sent" (state `after`, the pick): the by-wait pill, "Sent Nov 10, 08:48 CST". Gain: it is true. The top row already
  says "waits on lane glossary-pass", so the pill names only the send. It matches No. 58 and No. 44, which also have no
  answers row. Loss: No. 63 and No. 52 both wait on a lane but read differently ("Sent" against "Filing pending, sent").
  That difference is true: only No. 52 has a row the page can file.
- Option "Filing pending, sent" (state `filing`): the kept-answer pill. Gain: both lane cards read alike. Loss: it is false.
  `receipt()` (line 1514) reads receipts only with an answers row (`rc = savedOf(it) ? rcOf(it) : {}`), so the pill can never
  turn into "Filed in ...". It promises a step the page never shows (ux-statements-are-true).
- Pick: "Sent". Each option has a Hide control in the toolbar.
- The fold: the answer line is `lastAnswer`, so the fold holds the note and the reply only ("Show your note and the reply"),
  as the by-wait branch does (`threadEl(it, true)`).

## 3. Its place in Answered: newest first by `lastAnswer.at`

- What: `sentOf` returns `lastAnswer` for the item, so the section's sort (line 1200) places it by `lastAnswer.at`, newest
  first. No. 63 (08:48) sits above No. 58 (07:30), No. 52 (Nov 9, 19:59) and No. 44 (Nov 9, 12:40).
- Gain: one order for every card in the section. Loss: none.
- Pick: newest first, from the widened predicate in item 1. Without it, `sentOf` returns `{}` and the item sorts last.

## 4. The section count and the overview chips include it

- What: the Answered head reads 4, and the rail's Answered row holds chip 63 with the sent style. The rail reads "4 of 5 sent".
  Blocking reads 1 and holds chip 23 only.
- Gain: the rail, the tiers and the section agree. Loss: none.
- Pick: include. It follows from item 1; no separate code.

## 5. An item with a lane and a wait: no change (regression state)

- What: No. 58 (`lane`, `waits.pr`, `lastAnswer`, no answers row) already sinks by its wait today. It reads "Sent Nov 10,
  07:30 CST" and "waits on lane ci-cache-pin and PR #1402". State `both` focuses on it.
- Verdict: the widened predicate is true for it already, so nothing changes. The design reviewer checks it as a regression state.

## Checked

- Playwright, Chrome: all 4 states at 390, 800 and 1280, light and dark (24 runs). No script error, no sideways scroll.
  Focus ids `item-63`, `item-58`, `tier-holds` and (in `after` and `filing`) `pill-63` each find a box.
- `label_once.py` on the 4 states at 390: no hit.
- impeccable detector: no finding.
