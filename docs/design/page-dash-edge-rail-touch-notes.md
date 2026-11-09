# Waiting page, lane notes-fix-page: design notes

Mockup: `docs/design/page-dash-edge-rail-touch.html`. Screen: `skills/waiting-page/page.html` at main 174b005c1: the `.btn.dash` rule and the `.ov-head` rule.
Deep links: `#s=both|today|faint-edge|muted-edge|rows-every-pointer`, `&w=390|1280`, `&t=both|light|dark`, `&p=auto|coarse|fine`, `&lab=off`, `&hide=<state>,...`, `&focus=<id>`.
Sizes: phone 390 and wide 1280. `layout.py devices` prints `unknown` for this repo, so the sizes are the brief's 390 and the wide size of earlier waiting-page mockups. Themes: light and dark.
Focus ids: the edge `#b-none-chip-sizes`; a rail row `#ov-holds`.
Focus per choice: edge `#s=faint-edge&focus=b-none-chip-sizes` against `#s=muted-edge&focus=b-none-chip-sizes`; rows `#s=faint-edge&w=1280&p=fine&focus=ov-holds` against `#s=rows-every-pointer&w=1280&p=fine&focus=ov-holds` (the two row choices differ only for a mouse).
The page CSS in the mockup is page.html's style block at 174b005c1, as written. The lane's CSS sits in `#newcss`. Where the mockup and page.html differ, page.html and these notes win.
A desktop browser never matches `(pointer: coarse)`. The harness class `sim-coarse` mirrors the builder's rule in the frames that stand for touch. It is not for the builder.
No departure from the existing behaviour: both changes fix a gap against `docs/design/a11y.md`, as the two debts name.

## 1. Dashed button edge

Debt `alts-dash-edge-contrast` (dashed card buttons under 3:1). Rule: `a11y.md` contrast row, a control edge 3:1.
Measured edge against the card, WCAG ratio:

| Token | Light card | Dark card | Answered card (light / dark) | Ruling card (light / dark) |
|---|---|---|---|---|
| `--line` (today) | 1.35 | 1.33 | 1.26 / 1.25 | 1.30 / 1.39 |
| `--faint` (pick) | 6.00 | 5.51 | 5.60 / 5.16 | 5.75 / 5.76 |
| `--muted` (option) | 6.47 | 7.37 | 6.05 / 6.90 | 6.20 / 7.69 |

The ruling card is `--surface` 55% with `--ground` (line 722); the answered card is `--good-soft` 45% with `--surface`. A repo brand that sets `--r-ground-*` changes it: unmeasured for brand grounds.

- Pick: `--faint` on the base rule. Line 250 becomes `.btn.dash { border: 1.5px dashed var(--faint); background: transparent; color: var(--muted); font-weight: 500; }`. Gain: 6.0:1 light, 5.51:1 dark. It is the token that `.btn.dash.pkb` (line 346) and `.opt:hover` already use for a control edge, so it adds no colour. The pressed state (line 251) keeps its solid `--ink` edge, so shape still marks the state. Loss: the unpressed and pressed edges now differ less by colour (6:1 against 17:1 in light). Dashed against solid carries the state, as `a11y.md` asks (not colour alone).
- Wider reach: the base rule also draws Overturn on a ruling card (`b-over-<id>`, `buildCard` ruling branch). The mockup draws it. It passes on the ruling card in both themes.
- One home: with the base rule at `--faint`, lines 345 to 347 repeat it. Delete line 345 (its comment, which says `.btn.dash` uses `--line` and becomes false), line 346 (`.btn.dash.pkb { border-color: var(--faint); }`) and line 347 (`.btn.dash.pkb[aria-pressed="true"]`, which repeats line 251). Then edit the last sentence of the comment at line 350 to: "This rule stays after `.btn.dash[aria-pressed="true"]`: both have the same weight, so the source order decides." Checked: `.btn.pkb[aria-disabled="true"]` (weight 0,3,0) still beats `.btn.dash` (0,2,0), and it comes after line 251 (0,3,0), so an off Drop keeps its solid `--faint` edge.
- Option "Muted edge" (`#s=muted-edge`): the edge takes `--muted`, the label colour. Gain: 6.47 and 7.37. Loss: no precedent for an edge in `--muted`, and the edge draws as heavy as the label in dark. Hide it with "Hide Muted edge".
- The builder's check, from the debt: a browser test reads the computed edge colour of `#b-none-<id>`, `#b-done-<id>` and `#b-park-<id>` against the card surface. It reads `#b-over-<id>` against a ruling card. It checks light and dark, and fails under 3:1.
- Disabled: on a blocked card `.btn:disabled` sets opacity .45, so the edge falls under 3:1. WCAG 1.4.11 exempts a disabled control. No change.
- Forced colours: the browser draws the dashed edge in the system colour. No change.

## 2. Rail row height on touch

Debt `rail-row-touch-height` (rail rows 32px on touch). Rule: `a11y.md` target size row, 44 by 44 CSS px on touch, 24 by 24 for a mouse (owner ruling 2026-10-11, decision `ux-house-rules`).

- Pick: after line 86, `@media (pointer: coarse) { .ov-head { min-height: 44px; } }`. Same form as lines 149, 493 and 703. Measured in the mockup at 390: each row is 44px, the row is the whole width of the rail, and the page does not scroll sideways. It covers each `.ov-head`: the tier rows, Answered, Arbiter rulings (all from `renderRail`) and the Ask row (`askRailRow`). Loss: the phone rail grows 72px (6 rows at 12px), from 556px to 628px in the sample, so the first card starts lower. A touch tablet over 960px wide gets the same growth in its sidebar.
- Option "Rows 44 for every pointer" (`#s=rows-every-pointer`, best seen at `&w=1280&p=fine`): no media query. Gain: one rule. Loss: the mouse sidebar grows 72px too, where 32px already passes the 24px floor. Hide it with "Hide Rows 44 for every pointer".
- The builder's check, from the debt: a test in `skills/waiting-page/tests/page.test.mjs` reads each `#rail a.ov-head` height at 390 in a context with `hasTouch: true` (it matches `(pointer: coarse)` in Chromium; checked) and asserts 44 or more. A second context without touch asserts the row stays 32, so a mouse rail does not grow.

## 3. Rail number chips on touch

Lane ruling (owner, 2026-11-07 13:20 CST): a found gap gets a fix in this PR, not a note. Rule: `a11y.md` target size row, 44 by 44 CSS px on touch.
Today the rail chips (`.nchip`, line 88; `.pairchips .nchip`, line 95; the wide column form, line 104) are 32px tall at both widths, on touch too. The phone chip is 48px wide, so only the height falls short.

- Pick: after line 107 (the end of the `min-width: 961px` block), `@media (pointer: coarse) { .nchip, .pairchips .nchip { height: 44px; } }`. It must come after line 104, which sets `height: 32px` at the same weight (0,2,0). Measured in the mockup: each chip is 48x44 at 390 and 206x44 in the wide column on touch, and 32px with a mouse. With touch emulated in Chromium (`hasTouch: true`), the builder's rule itself, not the harness class, gives 44. No sideways scroll at 390. Loss: the phone rail grows 12px more per chip row: 566px to 686px in the sample, rows and chips together (120px). A group frame (`.pairchips`, 4px padding) grows to 52px.
- No width change: 48px on the phone already passes, and the wide chip fills the rail.
- The "Rows 44 for every pointer" option keeps chips at 44 on touch only.
- Focus: `#c-41` (`#s=today&focus=c-41` against `#s=faint-edge&focus=c-41`).
- The builder's check: the rail-row test also reads each `#rail .nchip` height at 390 and at 1280 in the touch context and asserts 44 or more, and 32 without touch.
