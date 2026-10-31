# Waiting page, lane page-shows-last-answer: design notes

Mockup: `docs/design/last-answer.html`. Screen: `skills/waiting-page/page.html` (main 42822fef). Lane kind: informed.
Deep links: `#s=page|edges|draft|open-1a|open-1b|receipt-2a|receipt-2b|receipt-2c|lane-3a|lane-3b`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Each option state has a Hide control.
The mockup draws with page.html's own `<style>` (lines 8 to 612 at 42822fef), plus the new rules in `#newcss`.

## Sizes and themes the page ships

- Media queries in page.html: `max-width: 400px` (tabs only), `max-width: 520px` (bar, viewer head),
  `max-width: 960px` (rail above the list), `min-width: 961px` (rail beside the list, chip titles), `pointer: coarse`.
- Drawn at phone 390 (covers the 400 and 520 rules), mid 800 and wide 1280. The check also opens 480.
- Themes: light and dark. `data-theme` on the root sets one; `prefers-color-scheme` sets the default.
- Checked headless (Playwright Chromium): 10 states, 4 widths, 2 themes. No horizontal scroll in the
  outer page or in any frame; each focus id is found. `lint/label_once.py` prints nothing for each state.

## New item fields, as drawn

- `lastAnswer` = {choice?: key | [keys] | "none", done?: true, note?: string, at: ISO time}.
- `reply`: a plain string. `lane`: a lane branch slug.
- A card may carry any subset. A card with none of them looks as today.

## 1. Where the last answer and the reply sit on an open card

- What: one calm panel, the thread (`.thread`, id `thread-<n>`): the last answer, a rule, then the reply.
  Shape of `.stake` (8px radius, 12px in) on `--chip`. No new colour.
- 1A (pick), `#s=open-1a`: after the stake lines (`holds`, `by`), before `context`.
  Gain: the urgency lines stay first on every card, so a scan down the list reads the same. The
  thread then says why the item came back, before the rewritten context. Loss: on a card with a
  design preview and both stakes, the thread starts lower.
- 1B, `#s=open-1b`: directly under the title. Gain: the reply is the first thing read. Loss: it
  pushes the Blocking and Upcoming lines down on only the cards that have a thread.
- Unsent draft (`#s=draft`): the thread stays in place while options are picked. Nothing in it changes.

## 2. Where the thread sits on a card with a receipt

Today `buildCard` returns right after `receipt(it)` when `isSaved(it)` is true, so a receipt card
shows only the top row, the title and the receipt. The builder adds the thread and the lane before
that return.
- 2A (pick), `#s=receipt-2a`: the receipt first, the thread below it. Gain: the receipt lands where
  it lands today, right under the title, so the held height (c193) works as it does now, and the new
  answer reads first. Loss: the order is not by time (new answer above the old one).
- 2B, `#s=receipt-2b`: the thread above the receipt. Gain: the order is by time. Loss: the receipt
  moves down by the thread's height, so it no longer lands at the place the c193 receipt ruling drew.
- 2C, `#s=receipt-2c`: no thread on a receipt card. Gain: the shortest card. Loss: the reply that
  the new answer responds to is gone until the owner presses Change.
- The same placement holds while the owner changes a saved answer (`state.changing`): the card is
  open again, so 1A applies.

## 3. Where the lane shows

- 3A (pick), `#s=lane-3a`: in the top row, after "waited ..." (or after the Answered pill), as
  `.onlane`: the weight and colour of "goes with No. 4" (`.inbundle`). Gain: no added height; it sits
  with the other facts about the item. Loss: small text, easy to miss.
- 3B, `#s=lane-3b`: a line under the title, the `.stake` shape with a `--line` border and no glyph.
  Gain: it reads at once. Loss: it looks like a stake line but means no urgency, and it adds one row.
- Not the red `.stake.holds` shape: `holds` says a lane waits on the owner; `lane` says the item
  waits on a lane. The tier and the controls do not change. The owner can still answer.
- The slug shows as written. GLOSSARY: a lane's branch slug is its name, so it is not machine text
  under ux-machine-text-hidden.

## 4. Copy

- Last answer head: "Your last answer, Oct 29, 14:05 CDT" (`fmt(at)`: US Central, 24h, zone named).
- Answer line, in `receipt()`'s words:
  - one key: "You chose B: One PR comment per red run." (`letterOf` and the option label)
  - `multi`: "You chose:" with the picks list; `ranked`: "You chose, in order:" with a numbered list
  - `none`: "None of these."
  - task: "Marked done." when `done` is true, else "Not marked done."
  - a key no longer in `options`: "You chose an option that is no longer listed." (never the raw key);
    a list with such a key: "You chose options that are no longer listed."
  - no `choice` on a decision: no answer line; the head and the note only.
- Note: "Note: <note>", as the receipt; the note "accepted pick" is not shown, as the receipt.
- Reply: "Reply: <reply>". Over 220 characters it clamps to three lines, as `.ctx` does, with the
  button "More of the reply" / "Less".
- Lane, 3A: "waits on lane <slug>"; 3B: "Waits on lane <slug>."
- Each head, reply and lane line is one text run that holds data, so none of them is a bare repeated
  label (ux-label-once). The thread's `aria-label` is "Your last answer and the reply", "Your last
  answer" or "The reply".

## 5. Points for the builder and the writer

- A reused key: if the writer rewrites `options` and keeps a key, the last answer names the new
  option's label, which is not what the owner chose. The page cannot tell. Fix in the writer: clear
  `lastAnswer.choice` when it rewrites options, or store the label with it. Pick: the writer clears it.
- An `at` that does not parse: `fmt` returns "". Pick: show "Your last answer" with no time.
- Reply length is unmeasured; the 37 live replies were not read. The clamp covers a long one.
- New CSS is in `#newcss`, labelled. `.receipt.last` extends the receipt (ux-variant-extends-home).

No item changes a spec or a ruling, so no item needs the owner's grant.
