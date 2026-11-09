# Waiting page, lane page-narrow-word-breaks: whole-word labels at narrow widths and large text (design notes)

Mockup: `docs/design/page-narrow-word-breaks.html`. Screen: `skills/waiting-page/page.html` at 390dd3f9 (PR 2383's head).
Designer kind: informed. Source of the defect: PR 2423's round-3 record, "Base defects" (comment 6742856907).
The mockup draws with page.html's own `<style>`, copied whole (`#pagecss`), plus this lane's rules (`#newcss`). Each state's markup is
what page.html drew from the page tests' fixtures (`PRESS_ASKS`, `FOLD_ROWS`, `PARK_A`, `PARK_B`, `DECISION`).
Each rule is scoped by an option's root class (`html.opt-fix`, `html.opt-wrap`); the builder drops that scope.
Deep links: `#s=asks|reply|bar|parked`, `&o=fix|wrap|today`, `&w=all|180|200|220|240|260|390`, `&z=100|150|200|300`,
`&t=light|dark`, `&lab=off`, `&hide=fix,wrap`. `z` sets the root font size, as the tests' `zoomText` does.
Focus ids: `#pick-fix`, `#pick-wrap`, on the first folded row with Dismiss. Link them with `z=300` (for example `#s=asks&o=fix&z=300`).
Sizes: 180, 200, 220, 240, 260 (a phone window at page zoom) and 390. `layout.py devices` prints `unknown` for this repo.
Themes: light and dark. No change differs by theme.

## 0. The defect, measured headless (Playwright Chromium, deviceScaleFactor 1, the fonts refused as in the tests)

Two causes, told apart by one experiment: set `overflow-wrap: break-word` on the labels and run the same states again.

- Cause A, the box has room but the track shrinks the press. `overflow-wrap: anywhere` makes each letter a break chance, so the
  min-content of a label is one letter. A track or flex item with a 0 minimum (`minmax(0, max-content)`, `min-width: 0`) then
  draws a press narrower than its own word. Example: Dismiss at 220 wide, 300%, and Send answers at 180, 200%. `break-word`
  alone fixes these.
- Cause B, one word is wider than its whole box at the reader's size. Example: at 180 wide, 300%, the ask list is 148 px and
  "Answered" at 42 px is about 190 px. No wrap rule fixes this: the word breaks, is clipped, or scrolls the page.
  `break-word` alone turns these into clipped labels (Send: "Sen" over "answe") or a page scroll (Dismiss and Send ask, 31 px).
- "W…" (folded titles): reproduced as "C… the S…" and "Y… re…" with the test fixtures. `.ftext` is clamped
  (`-webkit-line-clamp`, `overflow: hidden`) with no wrap rule, so each line holds the first letters of one word and an ellipsis.
  The reviewer's exact "W…" text is not in the fixtures; same rule, same cause.
- Parked Unpark (not in the step, found here): `.pkb > span` is `nowrap`, so "✓ Unpark" sets the press width. It runs past the
  window and the page scrolls sideways: 29 px at 180, 200%; 99 px at 180, 300%; 19 px at 260, 300%. At 150% it runs 29 px past
  its own block at 180 without a page scroll. "✓ Unpark" is 4.67em in the fallback font: the check glyph is wide.

## 1. Gap table: state x width x text size (light; dark is the same)

Today: words broken inside, page scroll. Target (option "Whole words, text fits its box"): none, at every cell.
Text size at the target is the section's 1rem after the cap (§3). 390 is drawn as a control: no gap and no change at any size.

| State | Width | 150% today | 200% today | 300% today | Ask text at target (150/200/300%) |
|---|---|---|---|---|---|
| Ask list, Ask box (`asks`) | 180 | Answere\|d, dismiss\|ed, Resto\|re | Repl\|y, Dismi\|ss, Answe\|red, 8 words | Ad\|d, Se\|nd, Ans\|wer, 25 words | 19.3 / 19.3 / 19.3 px |
| | 200 | dismisse\|d | Dismis\|s, Answer\|ed, Resto\|re | Sen\|d, Ans\|wer, 17 words | 22.9 / 22.9 / 22.9 px |
| | 220 | none | Answere\|d, Restor\|e | Repl\|y, Dismi\|ss, 9 words | 24 / 26.4 / 26.4 px |
| | 240 | none | dismisse\|d | Dismi\|ss, Answer\|ed, Waitin\|g | 24 / 30 / 30 px |
| | 260 | none | none | Dismis\|s, Answer\|ed, Restor\|e | 24 / 32 / 33.6 px |
| Reply box open (`reply`) | 180 | Sen\|d reply, repl\|y | Clo\|se, Se\|nd | as `asks`, 26 words | as `asks` |
| | 200 | dismisse\|d | Clos\|e, Sen\|d reply | 18 words | as `asks` |
| | 220 to 260 | none | Answere\|d (220), dismisse\|d (240) | Clos\|e, Sen\|d reply (220, 240) | as `asks` |
| Send bar (`bar`) | 180 | none | answer\|s | ans\|wers | bar: 24 / 28.6 / 28.6 px |
| | 200 to 240 | none | none | answe\|rs | bar: 24 / 32 / 33.3 to 42.9 px |
| | 260 | none | none | none | bar: 24 / 32 / 47.6 px |
| Parked lines (`parked`) | 180 | Unpark past its block, 29 px | Unpark past window, page scroll 29 px | page scroll 99 px | block: 16.0 / 16.0 / 16.0 px |
| | 200 | Unpark past its block, 9 px | page scroll 9 px | page scroll 79 px | block: 20.2 / 20.2 / 20.2 px |
| | 220 to 260 | none | Unpark past its block, 24 px (220) | page scroll 59, 39, 19 px | block: 24.5, 28.8, 33.0 px at 300% |

Checked on the mockup, 120 frames of the pick (4 states, 6 widths, 4 text sizes, plus dark at 300%).
Result: no word of a fixed label breaks inside. No page scroll. No press runs past the window or its parent's content box.
No label is clipped in its press. Every press is at least 44 by 44 px.
Checked on page.html with the rules appended: every state above plus the sent state, at 180 to 390 wide and 100 to 300%.
The same checks pass outside the item cards, apart from the sent-state items in §7. Also: no box moves at 360, 390, 820 and 1280 at 100%, and at
1280 at 200% and 300%. The one intended move: the waiting reply under a folded row gains its third line below a 19.5em list (§5).

## 2. Labels break only between words (both options)

- What: `overflow-wrap: anywhere` becomes `break-word`, with `hyphens: manual`, on the labels it breaks today.
- Gain: fixes cause A at every size. The press's min-content is its longest word, so no track draws it narrower than that word.
- Loss: alone, cause B labels clip or scroll the page (option "Whole words at the reader's size", `#o=wrap`).
- Pick: yes, with §3.

## 3. Text fits its box: one cap per section. Considered, not built

Ruling (coordinator, 2026-11-09 09:28 CST): build §2, §4 and §5 only. Part B (this section) is not built, so the page keeps
a11y.md's "Text size" rule. Reason: for a reader who chose large text, a mid-word break at 180 px and 300% is the smaller harm
than text that stops short of that size. Where one word is wider than its whole box, a mid-word break stays. The page must
never scroll sideways. The design below is kept so a later grant can build it.

- What: a section's text never runs larger than its longest fixed word allows. Three tokens on `:root`, in tokens.md's clamp() shape,
  each read by one section through a registered `--fit` (`@property`, `<length>`), so the `cqi` term resolves once, on the section:
  `--type-fit-asks` (binds on "dismissed" in Hide dismissed asks), `--type-fit-bar` ("answers"), `--type-fit-park` ("✓ Unpark").
  Floor: the default 16px (`min(1rem, 16px)`). Ceiling: the reader's size (`1rem`). Each rem font size in the section becomes
  `calc(var(--fit) * <the same number>)`, so the section shrinks as one and keeps its hierarchy.
- Gain: no label, date or title word breaks inside at 180 to 260 wide and 150 to 300% text; no page scroll. Text still grows with
  the reader's setting up to what the box holds: at 180 wide, 300%, the Ask section reads at 19.3 px, never under 16 px.
- Loss: the text in these three sections stops short of the reader's size where the window is too narrow for one word at that
  size. A reader at 300% on a 180 px window gets 16 px (parked block), 19.3 px (Ask section) and 28.6 px (send bar), not 45 to 48 px. Prose in these sections shrinks with the labels.
- Pick: yes. Departs from: a11y.md "Text size" (web text grows with the browser's default font size) for these three sections at
  180 to 340 px windows; the cap never takes text under the default size. Not blocking.
- Option "Whole words at the reader's size" (`#o=wrap`): §2 and §5 only. Gain: text keeps the reader's size. Loss: at 180 and 200,
  300%, Dismiss, Send ask and Unpark run past their box and the page scrolls sideways (31 to 99 px). The row date still breaks
  inside "Answered". Send answers clips to "Sen" over "answe".
- Hide controls: "Whole words, text fits its box", "Whole words at the reader's size".

## 4. Titles wrap by words, never cut to letters

- What: the clamped titles (`.frow .ftext`, `.askc.folded .fwait .ftext`) get `overflow-wrap: anywhere`. With §3 the title's words
  fit their line; only an owner's token wider than the whole line (a long path) breaks, at the line end, never cut to "W…".
- Gain: the row reads as words. Loss: none seen; the column is `minmax(0, 1fr)`, so `anywhere` changes no track size here.
- Pick: yes.

## 5. The waiting reply keeps three lines

- What: below a 19.5em list the folded row's title already clamps at 3 lines. The waiting reply under it clamps at 2,
  so "Your reply:" filled it and the reply's words never showed. It takes 3, as the row does.
- Gain: the reply's first words show. Loss: the row is one line taller (24.8 px at 100%), at 180 wide only at 100%.
- Pick: yes.

## 6. CSS change per selector (page.html at 390dd3f9)

| Selector | Today | Change |
|---|---|---|
| `.btn.send`, `.btn.fixw > span`, `.replyend .endrow > .btn`, `.older .uf-labels > span`, `.frow .fwhen`, `.frow .fgo` (both `@container askl` blocks), `.askrow .btn` (`@container askf (width < 16.5em)`) | `overflow-wrap: anywhere` (or none, on `.fwhen`) | `overflow-wrap: break-word; hyphens: manual` |
| `.frow .ftext`, `.askc.folded .fwait .ftext` | no wrap rule, clamped | `overflow-wrap: anywhere` |
| `@container askl (width < 19.5em)` | `.fwait .ftext` clamps at 2 (from the 30.5em block) | `.askc.folded .fwait .ftext { -webkit-line-clamp: 3 }` |
| `:root` | none | `--type-fit-asks: clamp(min(1rem, 16px), (100cqi - 72px) / 5.6, 1rem)`; `--type-fit-bar: clamp(min(1rem, 16px), (100cqi - 60px) / 4.2, 1rem)`; `--type-fit-park: clamp(min(1rem, 16px), (100cqi - 105px) / 4.4, 1rem)` |
| new `@property --fit` | none | `syntax: "<length>"; inherits: true; initial-value: 16px` |
| `.asks` | 1rem (inherited) | `--fit: var(--type-fit-asks); font-size: var(--fit)` |
| `.bar` | 1rem (inherited) | `--fit: var(--type-fit-bar); font-size: var(--fit)` |
| `.parked` | `font-size: .9375rem` | `--fit: var(--type-fit-park); font-size: calc(var(--fit) * .9375)` |
| In `.asks`: `.asks-head h2` 1.1875rem, `h2 .ct` .8125rem, `.asks-head p` .90625rem, `.askhint` .875rem, `.sline` .90625rem, `.ahead` .875rem, `.atext` 1rem, `.astate` .90625rem, `.askc .thread .lhead` and `.filed` .875rem, `.frow .fwhen` .875rem, `.frow .fgo` .90625rem, `.myreply .reply` 1rem, `.endrow .dwhy` .875rem, `.reline` .90625rem, `.unfold` .9375rem, `.thread .reply` .9375rem, `.morebtn` .90625rem | `N rem` | `calc(var(--fit) * N)`, same N (scope the shared `.thread .reply`, `.unfold` and `.morebtn` to `.asks`) |
| In `.parked`: `.parked > h2` .9375rem, `.pk-hint` and `.pk-why` .875rem | `N rem` | `calc(var(--fit) * N)` |

The px sizes in these sections (`.bar .st` 14.5px, `.stackh` 14px, `.stack .sstate` 14px) stay px; they never grew with text.
How the divisors were set: per section and window width, the largest section font that passes three checks (binary search,
180 to 390 wide). No fixed word breaks. No press runs past the window. No label clips. Each token's line sits under every measured point.
Named limit, font: measured with the tests' fallback font (DejaVu Sans); Atkinson Hyperlegible Next is not installed here, so its
widths are unmeasured. The Ask divisor sits about 1% inside its measured limit (19.3 px against 19.5 px at 180 wide). A wider page
font makes the binding word wider. Fix: none in the mockup; the builder's cases on CI's pinned Chromium decide, as for PR 2423's
5.6 divisor, and a red there adds headroom to the divisor. Until: 2026-11-21.

## 7. Found, not fixed (outside the step)

Widened by the coordinator's ruling (2026-11-09 09:28 CST): the lane also applies §2 to the card text (Park, Mark done, option
labels) and fixes the Unpark sideways scroll. The cap on `.card` below is part B and stays unbuilt.

- Item cards: Park, Mark done and None of these break inside a word at 180 to 220, 300%. Option labels ("Re|d", "Blu|e") break
  at 180 to 220, 200 to 300%. The context and steps text breaks at 180 to 200, 300%.
  The same cap on `.card` (about `(100cqi - 106px) / 3`, bound by the option label) would fix them.
  Card text is mostly px today. Owner grant: yes, to widen this lane.
- Prose in the Ask section shrinks with §3 and so wraps by words; prose elsewhere (card context) still breaks at 180, 300%.
- After a Send (the sent panel up): the page scrolls 9 px sideways at 180 wide at every text size, 100% too, and the answered
  card's line breaks "cho|se" at 180 to 220 at every text size. Both exist on the base, do not depend on text size, and are left
  alone here. The sent panel's presses (Undo send, Close) pass: whole words, inside their box, 44 px.

Review round 1 notes (2026-11-09), not fixed here:

- Code review: `overflow-wrap: anywhere` stays on `.pkb > span` and on `.frow .ftext`. Its stated reason for `.pkb > span` (the
  parked block must shrink) is unverified, since `.parked` is a size container. `.parked` sets `overflow-wrap`, which its
  descendants inherit; that is wider than the presses it targets.
- Triage sent more defects at narrow widths, outside this lane's scope until the coordinator says otherwise: the `.dcap` caption
  (PR 2423 reverts its rem caption; size it with the text and cap it at the title's size, or let it wrap), the failure line
  breaking "(permission|-denied)", and tab labels breaking mid-word ("Question|s") at about 180 to 310 px with 150 to 300% text.
- Font: widths were measured with the fallback font (DejaVu Sans); Atkinson Hyperlegible Next is unmeasured. Axe and the 24 px
  mouse target size were not run.

## 8. Shared with PR 2423 (merges first)

- PR 2423 adds `--dl-fs: min(.90625rem, calc((100cqw - 24px) / 5.6))` on `.sline.dline`, `.dsh-head h2` at `min(1.0625rem, 24cqw)`,
  and rules on `.askc.folded.withd .frow .ftext` and `.fwhen`, `.askc .thread .filed`, `.asklist .btn.fixw > .sz.vz`.
- After it lands, `--dl-fs`'s `.90625rem` reads `calc(var(--fit) * .90625)`, so the Restored line follows the Ask section's cap.
  One home: the section token sets the size; PR 2423's per-line cap stays only where its box is narrower than the section.
- `.dcap` (14 px at every text size) is PR 2423's; untouched here.

## 9. Checklist, both themes

- ux-text-zooms (guidance): pass with the departure in §3; text grows to the box, loses no content.
- ux-a11y-floor (touch size): pass; every press 44 by 44 px or more in all 120 frames.
- ux-fluid-tokens: pass; each clamp() is a `:root` token read.
- ux-component-reads-its-box: pass; the cap reads the section's box (`cqi`), no new media query.
- ux-label-once, ux-one-plain-name: no copy change.

Departs from: today's labels, which break inside a word at 180 to 260 px windows with 150 to 300% text. The cause is
`overflow-wrap: anywhere` on `.btn.fixw > span`, `.btn.send`, `.replyend .endrow > .btn`, `.askrow .btn`,
`.older .uf-labels > span` and `.frow .fgo`. It also departs from today's text size in the Ask section, send bar and parked
block, which follows the reader's size at any window width. Not blocking.
