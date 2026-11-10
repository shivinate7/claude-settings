# Waiting page, lane nfp-ux-text-zoom: how a row with a press picks its arrangement (design notes)

Mockup: `docs/design/press-row-reflow.html`. Screen: `skills/waiting-page/page.html` at the PR head baf62e9ae. The mockup's
`#pagecss` is that page's CSS, verbatim. `#newcss` is the change, scoped per option by a root class (`html.opt-fit`,
`html.opt-em`); the builder drops the scope. State `head` draws the PR head as built.
Deep links: `#s=fit|em|head`, `&w=all|1440|820|684|390|360|344|280|180|390x3`, `&t=light|dark`, `&z=1|2`, `&f=served|dejavu`,
`&lab=off`, `&hide=fit,em`. Text size sets the root font size, as the tests' zoom does. `390x3` is 390 wide at text 300%.
Sizes: 1440, 820, 684, 390, 360, 344, 280, 180, each at text 100% and 200%, and 390 at 300%. Themes: light and dark. Fonts:
served (Atkinson Hyperlegible Next, IBM Plex Mono, from `testing/fonts`) and DejaVu Sans. `layout.py devices` prints `unknown`.
Focus ids: `#pick-fit`, `#pick-em`. The options differ most at 344 wide, served, text 100%: link `#s=fit&w=344` and
`#s=em&w=344` (with `w` set, picture mode draws that one frame, and the frame carries the id).
Numbers below are from a headless Chromium run of the mockup, deviceScaleFactor 1. A browser that refuses fonts from disk
draws a fallback when the file is opened directly.

## 0. The defect at the PR head (state `head`), reproduced

- Text 200%, 684 to 1440 wide: the title column beside Dismiss or Restore is 0 to 41 px (served) and 0 px (DejaVu), and the
  press covers the row's text at 820 and 684. Cause: the one-line row (title, date, Show answer, press) is chosen by
  `@media (max-width: 520px)`, which text size does not move.
- 684 wide, text 200%, DejaVu: the page is 719 px wide in the mockup (the review read 722 on the full page).
- 344 wide, text 100%, served: rows stack under 20.375em of list, so the press drops with room to spare.
- Text 100%, DejaVu, 684 wide: the one-line title is 110 to 123 px, under 8rem. Main has the same.

## 1. How a row picks its arrangement. Owner grant: yes

Both options keep owner item 448 a: when narrow, the press drops under the text, at its start.

- Option "Rows take what fits" (`#s=fit`, pick). Each row wraps. A part moves to the next line only when the part before it
  would fall under its minimum. Order: the date drops under the title, then "Show answer" under the body, then the press under
  the row. The title's minimum is 8rem, or what the list can give where it is narrower (`min(8rem, 100cqi - 64px)`).
  - Gain: no width decides where a part goes, so every font and text size holds: the date or press drops exactly where the
    title would go under 8rem. Served rows at 344 to 357 stay beside their press (finding 2): 142 px at 344.
  - Loss: one markup change (section 2). A dropped press keeps the 2 px to the card's edge it has beside, not 8 px.
  - The glyph sits on the middle of the title, as main draws it at 360 and 390, at every width. The PR head's "glyph on the
    first line" and three-line title in the stacked row go: under the narrow look the title takes two lines, as main's.
- Option "Rows read their width in em" (`#s=em`). Main's 520 px row rules become `@container askl (20.375em <= width < 47em)`.
  The PR head's stacked rule stays under 20.375em.
  - Gain: no markup change. Holds at 200% and 300% in both fonts.
  - Loss: two numbers tuned to DejaVu Sans. Served rows at 344 to 357 still stack. At text 100% rows from 521 to 783 wide take
    the two-line form where main draws one line (684: title 482 px, main 177). Add to list and Send ask overlap at 344, DejaVu.
- Hide controls: "Rows take what fits", "Rows read their width in em".
- Pick: "Rows take what fits".

## 2. The pick, for the builder (CSS in words; `#newcss`, section "Rows take what fits")

- Markup: `askItem` wraps the glyph, title and date in `<span class="fbody">`. "Show answer" (`.fgo`) stays outside it.
- `.frow` is a wrapping flex row, centred: `.fbody` grows from 0, "Show answer" may shrink and wrap its two words. The glyph
  hangs in 24 px of start padding (padding on the parent, a matching negative margin on the glyph), so any part that wraps
  starts at the title's edge, 40 px in.
- `.fbody` is a wrapping flex row: the title grows from 0 with `width: 0` (a long title's length stays out of the row's
  minimum) and the 8rem minimum; the date wraps between "Answered" and the date, as PR 2253's wrap does.
- A row with Dismiss or Restore (`.askc.folded.withd`) is a wrapping flex row: the row button grows from 0, the press keeps its
  width and may shrink only when alone on its line. The card pads its start by `--lead` (28 px for Dismiss, so its label lines
  up with the title; 40 px for Restore, its edge) and the row button, the reply line and the done line pull back by the same,
  so a press beside the text sits where main puts it.
- The Dismissed line (`.askc.dropped .sline`) is a wrapping flex row with the same hanging glyph; its words take the 8rem
  minimum (select `> span:not(.g)`: the glyph is a span too).
- Only the look of a narrow list reads a width: main's 520 px rule as `@container askl (width < 30.5em)` (the list in a 520 px
  window at 100%). Under it: a two-line title, 8 px row padding, "Show answer" kept in the row's name on a row with a press,
  4 px end padding. It moves no part.
- The Ask box: its narrow form reads `@container askf (width < 28.375em)` (the box in a 520 px window at 100%). In it the row is
  a wrapping flex row: the hint and the slot each take a full line, Add to list sits at the start and Send ask at the end, and
  Send ask drops under Add to list only when the two no longer fit. This replaces the 16.5em rule. The hint keeps
  `max(66px, 3 * 1.55em)`.
- Remove: the row and Dismissed-line parts of both 520 px media blocks, the whole `@container askl (width < 20.375em)` block, and
  the Ask box's 16.5em block.
- Tests: the PR's "Dismissed line's glyph sits on the middle of its first text line" cases (`DROP_STACKED`) go red where the line
  takes two lines (280, and 360 at text 200%). Re-point them to "the glyph sits on the middle of the text block, as main draws
  it", under item 1's grant. No test or page code reads the row button's children by position, so `.fbody` breaks none.

## 3. Parked lines

- `.pk`'s side-column query is `37.5rem` at the PR head (600 px at 100%), so at text 200% the acts wrap under the line until
  the box is 1200 px. Unchanged here.

## 4. Measured (Chromium; the pick; light theme, dark at the four pinned sizes; title column of a row with a press, px)

| Size | Text 100%, served | Text 100%, DejaVu | Text 200%, served | Text 200%, DejaVu |
|---|---|---|---|---|
| 1440 | 385, beside (= head) | 331, beside (= head) | 599, beside | 575, beside |
| 820 | 313, beside (= head) | 259, beside (= head) | 527, beside | 503, beside |
| 684 | 177, beside (= head) | 337, beside, date under | 391, beside | 367, beside |
| 390 | 188, beside (= head) | 176, beside (= head) | 304, press under | 304, press under |
| 360 | 158, beside (= head) | 146, beside (= head) | 274, press under | 274, press under |
| 344 | 142, beside | 130 beside Dismiss; Restore under | 258, press under | 258, press under |
| 280 | 194, press under | 194, press under | 194, press under | 194, press under |
| 180 | 94, press under | 94, press under | 156, press under | 185, press under |

- No press covers a row's text, and Add to list and Send ask do not overlap, in any cell.
- 390 at text 300%: list 358 px, 7.5em, so no column can reach 8rem. The title takes the row (304 px, 6.3em), the press under.
- At 1440, 820, 390 and 360, text 100%, served, light and dark: every row, row button, press, title, glyph, Dismissed line, Ask
  box press and parked press keeps the PR head's box to 0.5 px. Those boxes are the PR's pins of main (`PINS`, `PIN_ASK`), so
  the PR body's promise holds. Not checked: `REPLY_PINS` (the reply form is not drawn; its rules are unchanged).
- The page scrolls sideways only at 180 wide with text 200%, in every state (head 236 px served, 274 DejaVu; pick 236 and 260):
  "Show 1 dismissed ask", the open card's head, the Ask box's text box and the parked presses keep their one-line widths. Not
  rows; not fixed here.

## 5. Departs from

Departs from: main's px breakpoint for the rows (`@media (max-width: 520px)` in page.html, `.frow` and `.askc.folded.withd`
rules), where a row now wraps by what fits. At text 100% that moves rows only where main's one-line title is under 8rem: from
521 to about 637 wide served, and to about 702 in DejaVu (from the 684 and 820 readings; the column grows 1 px per px). It departs from the PR head's stacked rule (20.375em: three-line title, glyph on the first line,
8 px under a dropped press) and its Ask box 16.5em rule. Not blocking.

## 6. Not drawn

- The tray's Send line (`.sline`), the stack of asks not sent (`.stack > li`) and the reply box's row keep their 520 px rules.
  Not measured at text 200% from 684 up; the builder's 200% tests should read them.
- The Send bar, item cards and `.rfoot` (each wraps today).
