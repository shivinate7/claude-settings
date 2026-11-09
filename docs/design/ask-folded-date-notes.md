# Waiting page, lane notes-fix-page: the date line of a folded answered row (design notes)

Mockup: `docs/design/ask-folded-date.html`. Screen: `skills/waiting-page/page.html` at main 422cbbdfe. Its CSS is copied
whole into the mockup (`#pagecss`). Only `#newcss` is new. There, each option is scoped by a root class
(`html.opt-date-wraps`, `html.opt-own-line`). The builder drops that scope.
Deep links: `#s=date-wraps|own-line|today`, `&w=all|1440|820|390|360`, `&t=light|dark`, `&lab=off`, `&hide=date-wraps,own-line`.
Sizes: 1440, 820, 390 and 360, as the brief names. `layout.py devices` prints `unknown` for this repo. Themes: light and dark.
Focus ids: `#pick-wrap` (option "Date wraps under the label") and `#pick-own-line` (option "Dismiss on its own line"),
on the first folded row. The options differ only at 520 px and narrower, so an item shows them at a phone width.

## 0. The defect (state `today`)

- `askItem` writes `.fwhen` as one string, "Answered Oct 30, 05:00 CDT". Under 520 px, `.frow .fwhen` keeps
  `white-space: nowrap` in a `minmax(0, 1fr)` column. So the line runs past its box.
- Measured on main with Playwright, fallback font: at 360 the text ends at x=252. Dismiss starts at 215, Restore at 211, and
  "Show answer" on a row with a waiting reply at 233. At 390 the text (252) runs past its box (237) and into Dismiss's box (245).
- Three rows have the defect, not one: a row with Dismiss, a row with Restore (dismissed list), and a row with a waiting
  reply (no side press). The mockup draws all three, with the open card above them.

## 1. Where the date goes under 520 px

- Option "Date wraps under the label" (`#s=date-wraps`, pick). The line may wrap, and it wraps between "Answered" and the
  date. The date moves whole. Dismiss, Restore and "Show answer" stay beside the row, as today and as the ask-dismiss
  design drew them. A row that fits keeps one line.
  - Gain: no overlap at 360 or 390 (the text ends at x=181; the nearest press starts at 215). Every folded row gets the same rule. It costs one line (22 px)
    only where the date does not fit: a row is 115 px at 360 against 93 today, for a two-line title.
  - Loss: needs one markup change in `askItem`, a span round the date. Without it, `white-space: normal` breaks
    "Answered Oct 30, 05:00 / CDT" or "Answered Oct / 30, 05:00 CDT" (measured).
- Option "Dismiss on its own line" (`#s=own-line`). A row with Dismiss or Restore turns into one column. The press goes
  under the date, at the text's start edge.
  - Gain: the date keeps one line on a row with a press. At 200% text zoom it holds better than the pick (see 3).
  - Loss: each such row grows 44 px (120 or 145 px at 360). The row with a waiting reply has no press, so it still needs the
    date span and the wrap. So this option is the pick plus more change.
- Hide controls: "Date wraps under the label", "Dismiss on its own line". The waiting page stamps its own letters, so no option has one.
- Rejected, not drawn: smaller type or less padding on Dismiss. The press keeps the box of "Dismissing…" (`.btn.fixw`,
  ux-press-moves-nothing), so it is 120 px wide. Trimming its 10 px side padding frees at most 20 px. That is less than
  the 37 px the date overlaps at 360. A smaller font fails ux-text-zooms.
- Departs from: nothing the owner sees at 1440 or 820. Under 520 px the date line can take two lines, where today it takes
  one (and overflows). Not blocking.

## 2. What the builder touches (pick)

- `askItem`: `.fwhen` becomes `"Answered"`, a space, then `<span class="fdate">` holding the date (`fmt(t.answered)`). With no date, it stays
  "Answered" alone. The text is unchanged, so `textContent` reads as before.
- CSS, in the existing `@media (max-width: 520px)` block with `.frow`:
  `.frow .fwhen { white-space: normal; min-width: 0; }` and `.frow .fdate { display: inline-block; }`.
  `inline-block` keeps the date whole when it fits a line, and lets it wrap inside itself when it is wider than the line.
- Nothing above 520 px changes. Checked: every folded row's geometry at 1440 and 820 matches `today`, light and dark.

## 3. Found, not fixed: 200% text zoom at 360 (ux-text-zooms)

- At 180 CSS px (360 at 200% zoom), the text column of a row with a side press is 0 px wide on main and with the pick.
  The 120 px press and the gutters take the row. With "Dismiss on its own line", every row with a press reads, but the
  row with a waiting reply still has no room beside "Show answer".
- A fix might add a narrow rule (for example at 300 px and under) that drops the press under the row and "Show answer" with it.
  That is a separate change. The page has no measure for it today.
