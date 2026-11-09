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
  A folded row with Dismiss or Restore beside it keeps that floor from 30.5em to 40em too (`askl (30.5em < width <= 40em)`): the date,
  "Show answer" and the press leave the title 0 px at 530 wide and 65 px at 600. From 40em (640 px) the title has about 129 px or more
  beside them. Measured at a 641 px list (673 px window) with the page's own date text: the least found is 129 px (129.4), beside Restore
  with "Answered May 30, 00:00 CDT", 1.4 px over the 128 px floor. Not every date was tried. Up to that width the row takes the phone arrangement, "Show answer" in the button's name only.
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
  (`max-inline-size: 100%`), so neither sets a press's height. A press holds its resting height while its write waits, at every
  text size. Its resting verb wraps in a narrow press (at 180 wide with text doubled, 117 px tall). A second hidden copy of the verb
  (`.sz.vz`) wraps the same way and keeps that height under the clipped busy label. At the default size that is 44 px at 180 wide, busy or
  not. A waiting press is `aria-busy="true"` (askPress sets it, and it goes when the write ends); its name stays "Dismiss: ...".
  Show answer takes 12 px of the row's end padding at 180 wide so it stays on one line (a bandaid for that one width; at larger text it wraps inside the window).
- The room under the page follows the send bar's real height (`--bar-h`, set from the bar by a `ResizeObserver`), never under 96 px.
  So the bar covers no list element where it wraps and grows at 180 to 360 wide with text doubled or tripled. The Status view's
  copy notice (`.sv-toast`) sits that same room above the window's foot (`bottom: var(--bar-room)`), so it never covers the bar.
- At 180 to 320 wide with text doubled or tripled, no element sets the width of the Ask box or the list: `.asks-body`, `#askList`
  and `.asks-head` have one `minmax(0, 1fr)` track. The Show dismissed toggle's words break inside it, the Questions heading wraps,
  and a card's waiting line (`.astate`) breaks anywhere, so no word sets the card's width.
- Under `16.5em` of the Ask box or reply form, a press's word that is wider than the box breaks inside it (`overflow-wrap: anywhere`).
  So at 180 and 220 wide, doubled or tripled, "Close" and "Send reply" stay inside their presses, and the presses inside the card.

## 7. Named limits at narrow widths and large text (lane uxz-base-gaps)

- The tab bar is one row that scrolls on its own. A tab is never wider than the strip (`.tabs` is a size container; each tab has
  `max-inline-size: calc(100cqw + var(--in-l) + var(--in-r))` and `overflow-wrap: anywhere`). 100cqw is the bar's content box, 32 px
  narrower than the strip, so the cap adds back the bar's side padding (`--in-l`, `--in-r`, the `.in` gutters). A label wraps inside its
  tab. A word breaks mid-word when it does not fit its line. A word narrower than the strip can break too, because the count chip
  shares the line. "Questions" is 157 px against 166 to 186 px of room at 180 to 200 wide at 200% text. Measured on the built page.
  The 23 harness widths are 180, 190, 200, 210, 220, 240, 260, 280, 300, 320, 360, 390, 430, 480, 520, 540, 560, 600, 640, 700, 820, 1024
  and 1280. Five more were added for the range ends: 225, 230, 250, 270 and 275. "Questions" breaks at 180 to 200 wide at 200% text.
  At 300% it breaks at 180 to 278. "Designs" breaks at 180 to 230 at 300%. "Status" and every label at 100%, 150% and 390 wide or
  more never break. A lone letter appears at 190 to 200 wide at 200% ("Question|s") and at 253 to 278 at 300%. Both ends of the 253 to 278 range were measured at every integer width. For "Designs" it
  appears at 210 to 230 at 300% ("Design|s"). A named limit; fix: step `page-narrow-breaks-rest`. The page
  before this lane never broke a tab label: its tab ran wider than the strip, and the bar scrolled. When the Designs sheet closes,
  `revealTab()` scrolls the selected tab fully into the bar, as a tab press does.
- The Designs sheet's head wraps (`.dsh-head .in`, `flex-wrap: wrap`). The title's basis is 0 and its floor is 4em (`min-width: 4em`),
  so the row breaks where the buttons leave the title under 4em. The title keeps the first line, alone if no button fits beside it.
  Then the last buttons take a second line and Close sits at its end, inside the window. Prev and Next sit in one box (`.dnav`), so they
  wrap as a pair, never one on each row. The head takes a third row
  at 180 to 210 wide at the default text, at 125% and at 150%. At 200% it does so at 180 to 220, and at 300% at 180 to 280. Measured
  at 180, 190, 200, 210, 220, then 240 to 300 in steps of 20, on the built page. Row 3 holds Close alone at 180 to 210 at the default text, at 125% and
  at 150%, and at 260 to 280 at 300%. It holds Open full size and Close at 180 to 220 at 200% and at 180 to 240 at 300%.
- The title's text grows with the root size, `min(1.0625rem, 24cqw)`: 17 px at the default text, 21.25 px at 125%, 25.5 px at 150%, 34 px
  at 200%. The cap, 24% of the head's content width, keeps 4em of the title inside one line of the head. It sets the size only at large
  text in a narrow window: at 300%, 35.5 px at 180 wide, 40.3 at 200, 45.1 at 220 and 49.9 at 240, not 51 px. There the title is
  148, 168, 188 and 208 px wide, at least 4em (142, 161.2, 180.4 and 199.6 px).
- Measured window widths, in 10 px steps, at the default text: the head is two rows at 220 to 320 and 530 to 620, one row at 330 to 520
  and from 630 to 1280. At 320 the title is 114 px (66 px on the page before this lane); at 580 to 620 it is 105 to 145 px (19 to 59 px
  before). At 125% text it is two rows at 220 to 340 and 650 to 730; at 150%, at 220 to 360 and 770 to 840. At 220 and 240 wide Close
  was outside the window, or 2 px from its edge, before.
- The send bar's status has two numbers. The CSS floor is 2em (`.bar .st`, `min-width: 2em`): 27 px at 520 wide or less (13.5 px text),
  29 px above (14.5 px text). The tests measure 4em at 180 and 390 wide at the default text: 54 px at both widths (13.5 px text). The
  status is that wide or sits on its own line. Where the buttons would leave it under 2em, they wrap under it and it takes the line
  (window widths in 5 px steps up to 225, then 10 px): at 180 to 205 wide at the default text, at 180 to 230 at 125% text, at 180
  to 260 at 150%, at 180 to 300 at 200%. At 180 to 390 at 300% (measured at 10 to 40 px steps; 280 and 300 wide at 200%, 360 and 390 at 300%).
  At 220 at the default text it stays
  beside Send answers, 41 px wide, as before.
- An answered thread has one `minmax(0, 1fr)` track (`.thread`), and its reply, filed path and the owner's note (`.rnote`) break
  anywhere. So a long unbroken token stays inside the card and never scrolls the page. The note's wrap breaks the token; the track keeps
  any child that does not wrap from setting the thread's width. With neither, a 60-character token in the owner's note makes the thread
  477 px wide at 180 wide.
- After a Restore, the "Restored." line keeps its words whole where it can. Its text is the line's size (`.90625rem`), capped at the
  text column over 4 (`--dl-fs` on `.sline.dline.dok`, a size container; the "Not restored" and "Not dismissed" lines are not `dok`, so
  they keep the reader's size). The word is written with a soft hyphen ("Re&shy;stored.") so it may break there and nowhere else.
  `overflow-wrap: anywhere` stays as the last resort, so a wider font breaks a word inside the window, never past it. The glyph sits on
  the first line: the line's items start at the top, the glyph is moved to the middle of the first line box. The row is centred in
  the 44 px floor, so a line that does not wrap looks as before. On every status line that wraps (the Restored line and both failure
  lines) the glyph moves up from the middle of the whole line to the first line. Measured against the page before this lane, the move is 11 to 22 px for the Restored line.
  For the failure lines at 210 to 360 wide at the default text, the move is 11 to 34 px. The move is 14 px or more at
  125%, and 33.7 px at 1280 wide at 300%. A line of one row does not move.
- The cap sets the size at 180 to 205 wide with text doubled and at 180 to 260 wide with text tripled (window widths in 5 px steps).
  At both it is 22.5 px at 180, 25 at 190 and 27.5 at 200. With text tripled it is then 30 at 210, 32.5 at 220, 35 at 230, 37.5 at 240,
  40 at 250 and 42.5 at 260 (29 and 43.5 px uncapped). At the default text, 125% and 150% it never sets the size from 180 wide up (21.75 px
  at 150%, against a 22.5 px cap at 180). The page before this lane drew the word wider than its column at 180 to 225 wide doubled and
  180 to 290 wide tripled. The word ran past the window at 180 to 190 doubled and 180 to 260 tripled.
- The failure line breaks inside "(permission|-denied)" at 180 wide at 100% text, 180 to 200 at 125%, 180 to 225 at 150%. It breaks at 180 to 270 at
  200% and 180 to 360 at 300%. PR 2383 broke it after the hyphen. The cause is the 88 px `.sline.dline` column at 180 wide at 100%.
  A named limit; fix: step `page-narrow-breaks-rest`.
  The failure lines also break inside "denied" ("denie|d") at 180 wide at 200% and at 210 to 230 at 300% ("deni|ed" or "den|ied" at 180
  to 205 at 300%). They also break inside "dismissed" ("Not dis|missed"), "restored" and "(permission" ("(per|mission") at 180 to 190 wide at
  150%, 180 to 220 at 200% and 180 to 300 at 300% ("(permission" to 210 at 150%, 240 at 200% and 320 at 300%; "restored" at 180 at
  150%, 180 to 200 at 200% and 180 to 260 at 300%). The page before this lane did not break these words and ran past the window there:
  the page scrolled sideways at 180 to 190 at 150%, 180 to 220 at 200% and 180 to 320 at 300%.
- Departs from: the page before this lane (PR 2383's head) in eight places, as window widths in 10 px steps (5 px under 225). Folded rows with Dismiss or Restore take the phone
  arrangement at 530 to 670 at the default text, 650 to 830 and 970 to 1100 at 125%. They take it at 770 to 960 and from 1040 up to 1920 at 150%.
  The Designs head takes a second row at 220 to 320 and 530 to 620 at the default text, 220 to 340 and 650 to 730 at 125%. It takes a second row at 220 to 360 and 770 to 840 at 150%. Its title is larger at every width at 125% and 150%. Its third row is new at 180 to 210 at the default text, at 125% and at
  150%, 180 to 220 doubled and 180 to 280 tripled (Close alone, or with Open full size at 180 to 220 doubled and 180 to 240 tripled). The position "1/2" is smaller than before at 180 to 230 wide tripled (35.5
  to 47.5 px, not 48), where it takes the title's cap. The bar status takes its own line at 180 to 205 at
  the default text, 210 to 230 at 125%, 240 to 260 at 150% and at 300 at 200%. It did so before at 180 to 205 at 125%, 180 to 230 at 150% and 180 to 280 at 200%. The
  glyph of the Restored line and of both failure lines is on the first line of a wrapped line, not in the middle of it, at every text size. The
  "Restored." line is smaller than its text at 180 to 205 doubled and 180 to 260 tripled, and spells "Re-stored." with a soft hyphen; at
  the default text and 125% its size and spelling do not change. At 150% the line splits "Re-" and "stored." at 180 to 190 wide. A tab wraps
  its label inside the strip (a cap at the strip's width). It breaks a word that does not fit its line: a word wider than the strip, or a narrower one when the count chip shares the line, at the widths in the tab bar paragraph above. The failure lines break
  inside "dismissed", "restored" and "(permission" at the widths in the failure-line paragraph above.
