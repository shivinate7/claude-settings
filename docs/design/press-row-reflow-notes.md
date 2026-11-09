# Waiting page, lane nfp-ux-text-zoom: rows with a press at narrow widths and large text (design notes)

Mockup: `docs/design/press-row-reflow.html`. Screen: `skills/waiting-page/page.html` at main 2ac382cc6, plus PR 2253's pick
(folded row date wraps: `.frow .fwhen` wraps, `.frow .fdate` is inline-block). PR 2253 is not merged yet. Without it, the date
line runs under Dismiss at 360 and 390 again. The page CSS is copied whole (`#pagecss`). Only `#newcss` is new. Each option is
scoped by a root class (`html.opt-start`, `html.opt-full`). The builder drops that scope.
Deep links: `#s=start|full|today`, `&w=all|1440|820|390|360|280|240|180|360x2`, `&t=light|dark`, `&z=2`, `&lab=off`,
`&hide=start,full`. `360x2` is 360 wide with the root font size doubled. 280, 240 and 180 are page zoom on a narrow window.
Sizes: 1440, 820, 390 and 360 (the brief), 280, 240, 180, and 360 with text at 200%. `layout.py devices` prints `unknown`.
Themes: light and dark. Focus ids: `#pick-start`, `#pick-full`, on the first folded row with Dismiss. The options differ only
where a row is narrow for its text, so link them with `z=2` (for example `#s=start&z=2`).

## 0. The defect (state `today`), measured headless, deviceScaleFactor 1

- Text column of a folded row with Dismiss: 146 px at 360, 66 at 280, 26 at 240, 3 at 180. The Dismissed line: 151, 71, 31, 7.
- Add to list and Send ask overlap at 280, 240 and 180 (`.askrow` at 520 and under: `minmax(0, 1fr) auto`, both `nowrap`;
  Send keeps the box of "Send 99 asks", 138 px). At 180 the page also scrolls sideways (200 px wide).
- Dismiss and Restore did not overlap each other in any drawn row. The press that overlaps is Send ask, over Add to list.
- Root font size doubled at 360: no text grows (54 text boxes stay under 24 px), because page.html sizes text in px
  (`body { font: 16px/1.55 }`, `.frow .fwhen { font-size: 14px }`, and so on). Only rem values move, such as `.pk`'s
  `minmax(19rem, auto)`.
- Today's rules, cited at main 2ac382cc6: `.askc.folded.withd` (grid `minmax(0, 1fr) auto`), its 520 px block
  (`.askc.folded.withd .frow`, "Show answer" visually hidden), `.askc.dropped .sline` and its 520 px block (Restore kept in
  column 3), `.frow` and `.frow .fgo` at 520 px, `.askrow` at 520 px, `.btn.fixw` (the press keeps the box of its busy label,
  so Dismiss is 120 px), `.pk` with `@container (min-width: 600px)`.

## 1. Text in rem (both options). Owner grant: yes

- What: each font size in the drawn rows moves from px to rem at the same value (16 px = 1rem), plus `.ans`'s line height,
  so the sent badge's words stay in its pill.
- Gain: the browser's default font size and text zoom reach the text (ux-text-zooms, a11y.md "Text size"). At 100% nothing
  moves: every box at 1440, 820, 390 and 360 matches `today` to 0.1 px, light and dark.
- Loss: a page-wide change. The mockup converts only the parked block and the Ask section. The other tiers stay px until a
  lane converts them.
- Pick: yes. Departs from: page.html's px font sizes (`body`, `.frow .fwhen`, `.sline`, `.ahead`, `.parked` and others). Not
  blocking.

## 2. When a row has no room for its text beside the press (pick: "Press under the text, at its start")

- Breakpoint, both options: the ask list and the Ask box become query containers. A folded row or a Dismissed line stacks at
  `@container (width < 19.5em)` (312 px at 100% text, 624 px at 200%). The Ask box stacks at `width < 16.5em` (264 px).
  In em, so larger text trips it sooner (ux-component-reads-its-box). No new media query.
- The 520 px phone rules of the same parts read their box too, with each floor equal to the 520 px window's content at 100% text:
  the folded row, `.fwait` and the Dismissed-row block at `askl (width <= 30.5em)` (488 px); the Ask box at `askf (width <= 28.375em)`
  (454 px); the reply box's Close at `askf (width <= 26.75em)` (428 px); the Designs viewer's head at `dsh (width <= 30.5em)`.
  The 19.5em and 16.5em floors above stay. At 100% text each box is the same as the 520 px rule drew it at 320, 390 and 1280.
- Readable minimum: 8em of text column beside a press (128 px at 100%, 256 at 200%). 360 keeps 146 px, so it stays beside.
- Stacked row: the row button is two columns (glyph, text). Title up to 3 lines, then the date, then "Show answer" on a row
  with no side press. On a row with Dismiss or Restore, "Show answer" stays in the button's name only, as today's phone row.
  The glyph sits on the title's first line (`align-items: start`), not on the middle of the block.
  The press may shrink below its busy label's box (`grid-template-columns: minmax(0, max-content)`), never past the row.
  A busy label ("Restoring…") wider than its press clips to one line with an ellipsis for the moment it shows.
  Loss: at 180 px with text tripled it shows about two letters and the ellipsis (96 of 293 px).
- Option "Press under the text, at its start" (`#s=start`, pick). The press keeps its width. Dismiss (quiet) keeps its label
  centred in its box, as on main. Restore (outlined) lines its edge up with the text (40 px). Add to list and Send ask stack at the
  start. Gain: the quiet act stays quiet; the row reads as today's, one line taller. Loss: a ragged right edge.
- Option "Press under the text, full width" (`#s=full`). The press spans the row inside 16 px. Dismiss gets a `--line` edge,
  or a full-width quiet press reads as floating text. Gain: the biggest target. Loss: Dismiss looks as loud as Reply,
  every stacked row gets a box, and a boxed Dismiss on a folded row differs from the quiet Dismiss in the open card.
- Hide controls: "Press under the text, at its start", "Press under the text, full width".
- Departs from: today's rows under 312 px and at large text, where the press sat beside a 0 to 66 px column. Not blocking.

## 3. Parked lines. Owner grant: yes

- What: `.pk`'s side-column query moves from `600px` to `37.5rem`. That is the same at 100%, and with text at 200% the acts
  wrap under the line until the box is 1200 px.
- Gain: with rem text, `minmax(19rem, auto)` is 608 px. On the 600 px query, a box of 600 to 750 px would leave the line
  0 to 126 px. Loss: none at 100%.
- Departs from: `.pk` `@container (min-width: 600px)`. Not blocking.

## 4. Checked headless (Playwright chromium, deviceScaleFactor 1), both options, light and dark

| Size | Overlap | Text column of a row with a press | Page scroll |
|---|---|---|---|
| 1440 | none | 355 px (same as today) | none |
| 820 | none | 283 px (same as today) | none |
| 390 | none | 176 px (same as today) | none |
| 360 | none | 146 px (same as today) | none |
| 280 | none | 190 px (stacked) | none |
| 240 | none | 150 px (stacked) | none |
| 180 | none | 90 px (stacked; under the 8em minimum: the card's own padding and the glyph take the rest) | none |
| 360, text 200% | none | 270 px (stacked; at least 256 = 8em) | none |

## 5. Not drawn

- `.stack > li` (asks not sent yet) and the reply box's `.askrow`. They take the same rules: the reply box's row is an
  `.askrow` inside `.askform`'s container, so it shares 2b's `16.5em` query. There it keeps the arrangement the 520 px rule
  gives it: the hint on its own line, then Close (`.btn.rx`) at the start and Send reply at the end of one line. Under
  `12.5em`, where those two no longer fit side by side, Send reply takes its own line and Close the next. The Send bar, item
  cards and `.rfoot` (each is flex-wrap today).

## 6. The rule at narrow widths and large text

- The Ask box rule (`askf (width <= 28.375em)`) applies to the Ask box only (`:where(.askform:not(.replyform))`). The reply form is an
  `askf` container too, and has its own stacked arrangement from `26.75em` (its content in the 520 px window). At 530 and 546 wide
  at the default text the reply form is wider than that, so Close sits left of Send reply on one line, as main draws it.
- The Designs head's position reads `1/2` or `1 of 2` by the `dsh` container: its `30.5em` rule sets `--pos-short` on `#dPos`,
  and the script reads that custom property. The script sets the text, because the tests read it as text.
- In the ask list, a press's hidden sizer ("Dismissing…", "Restoring…") and its busy label (`.busy`) each clip on one line
  (`max-inline-size: 100%`), so neither sets a press's height: the presses stay 44 px at 180 wide, busy or not. Show answer takes
  12 px of the row's end padding at 180 wide so it stays on one line (a bandaid for that one width; at larger text it wraps inside the window).
- The room under the page follows the send bar's real height (`--bar-h`, set from the bar by a `ResizeObserver`), never under 96 px.
  So the bar covers no list element where it wraps and grows at 180 to 360 wide with text doubled or tripled. The Status view's
  copy notice (`.sv-toast`) sits that same room above the window's foot (`bottom: var(--bar-room)`), so it never covers the bar.
- At 180 to 320 wide with text doubled or tripled, no element sets the width of the Ask box or the list: `.asks-body`, `#askList`
  and `.asks-head` have one `minmax(0, 1fr)` track. The Show dismissed toggle's words break inside it, the Questions heading wraps,
  and a card's waiting line (`.astate`) breaks anywhere, so no word sets the card's width.
- Under `16.5em` of the Ask box or reply form, a press's word that is wider than the box breaks inside it (`overflow-wrap: anywhere`).
  So at 180 and 220 wide, doubled or tripled, "Close" and "Send reply" stay inside their presses, and the presses inside the card.
