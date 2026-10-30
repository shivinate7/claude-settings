# Waiting page, arbiter rulings: design notes

Mockup: `docs/design/arbiter-ruling.html`. Screen: `skills/waiting-page/page.html` (5d8ca121).
Ruling: `session-tiers`, Arbiter, "On the page" (owner, 2026-10-30 12:44 CDT, waiting item 86).
Deep links: `#s=collapsed|open|pressed|sent`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=collapsed,open`.
The mockup holds page.html's `<style>` lines 8 to 612, word for word. New CSS sits after it.
`layout.py devices` prints "unknown" for this repo. The sizes come from the brief and page.html's
media queries: phone 390 (≤520), mid 800 (≤960), wide 1280. Light and dark.

## 1. Section: name, place, order

- Name "Arbiter rulings". It uses the glossary terms `arbiter` and `ruling`. Its glyph is a hollow
  diamond (`.g.ruled`). No other section uses that shape.
- It sits after the open tiers, after Pick stands. It shows only when one ruling or more exists, as an
  empty tier hides today (`renderList`, `if (!items.length) return`).
- Rulings show newest first, by `ruled`. A new ruling lands at the top. A press re-ranks nothing.
- A line under the head: "Each stands unless you overturn it."
- Rail: one row, glyph and name and count, with no chips. Its aria-label is "2 rulings, Arbiter rulings".
- Gain: the section is quiet, and a reader finds it at once. Lose: no chip per ruling in the rail.
- Pick: as drawn.

## 2. Collapsed on load

- A (`#s=collapsed`): the section shows closed on load. The head is a button in the `h2` with
  `aria-expanded`. When closed, the line adds "Newest Oct 30, 12:44 CDT.". The owner sees new rulings without opening it.
  Gain: rulings never compete with asks, and the list stays short as rulings collect. Lose: Overturn needs one press more.
- B (`#s=open`): the section shows open on load. Gain: each ruling shows. Lose: the list grows with each ruling.
- A section with a pressed Overturn in the viewer's draft loads open (`ux-keep-what-was-made`).
  The open or closed choice may stay in `localStorage` as a per-viewer convenience.
- Pick: A.

## 3. The ruling card

- It shows, in this order: "No. 91", "ruled Oct 30, 12:44 CDT", the title, the ruled option as its
  letter chip and label, the why, a reserved ready line, then a foot row: "Recorded in <home>." and Overturn.
- Ruled time: page.html's `fmt(it.ruled)`. That is US Central, 24-hour, and it says CDT or CST. There is no second formatter.
- Quiet: the card has a lighter ground, a 17px title, no tier edge and smaller padding. The why uses muted text.
- Only the option the arbiter ruled shows. The other options do not show (not drawn).
  Gain: a short card. Lose: to see the other options, the owner must open the record.
- Record id: page.html already shows `home` in `.dest` (`buildCard`, "Lands in …"), so the card does the same.
  This goes against house rule `ux-machine-text-hidden` (a record id shows only in a closed disclosure). That conflict is on the page today too.
- Pick: as drawn.

## 4. Overturn

- The button is `.btn.dash`, a toggle like "Mark done" and "None of these" (`buildCard`). Its visible
  text is "Overturn", and its aria-label is "Overturn the ruling on No. <n>". It shows `aria-pressed`.
- Pressed (`#s=pressed`): the card takes the accent inset ring, as `.opt.sel` does. The ready line
  reads "Ready to send: overturn.", and the bar reads "1 ready (1 overturn). 2 stay open." / "Send 1 answer".
  A second press clears it. The ready line and the button keep their boxes, so a press moves nothing (checked: same card height).
- Send writes `answers/<id>` with `choice: "overturn"`, through `sendAll`. Undo send (8 s) restores it as a pending draft, as for a pick.
- Sent (`#s=sent`): the card uses the answered style, "Answered, filing pending <time>", then
  "Answered, filed in <home> <time>". The receipt line reads "You overturned B: <label>.", and it keeps Change, as for a sent pick (`receipt`).
- Pick: as drawn.

## 5. Counts

- A ruling is not open. It is not counted in "N stay open", in the Questions tab count, in "All answered."
  or in the rail's "of N sent" and "ready to send". A pressed Overturn counts in the bar's "ready" only, so
  Send shows its count and the rail never passes 100%.

## 6. For the builder (contract as given; not changed here)

- `by` is already the deadline field (`rawTier`, `buildCard`: `it.by && validT(it.by)`). Test `by === "arbiter"`
  exactly, and keep rulings out of `rawTier` and the deadline line. See Input Needed in the lane report.
- The filter at `items` `onSnapshot`: keep `status !== "closed" || (status === "closed" && by === "arbiter")`.
- `"overturn"` is not an option key. These need a branch: `draftReady`, `readyText`, `receipt`, `choiceText`
  (noticeText "91 overturn"), `answerLine`, and the Undo notice. That notice says " are open again." For an overturn,
  "the ruling stands again" is true. The writer refuses an option keyed `overturn`, as it refuses `none`.
- `problem()` must pass a closed ruling. Its picture and stake checks do not apply.
- The sample store holds a closed item, No. 88, that is not by the arbiter. The mockup hides it.
