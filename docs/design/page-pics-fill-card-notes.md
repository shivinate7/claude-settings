# Waiting page: an option's picture fills its card

Mockup: `page-pics-fill-card.html`. Screen: `skills/waiting-page/page.html` at ddaa393c0 (`optPic`, `fitFrame`, `MIN_PIC`, `PHONE_H`, `.opt .opic`). Owner, 2026-11-09 20:47 CST: "the images are so small in the artifact cockpit." The mockup puts page.html's own CSS in `#pagecss`, unchanged, and only this step's notes in `#newcss`: the pick changes no CSS rule.

Measured with headless Chromium (Playwright), deviceScaleFactor 1, at 390, 1280 and 2200 wide, light and dark: 246 runs (6 cases × 6 height rules × 3 sizes × 2 themes, plus the 1x upscale on the focus case). Each frame is as tall as its page, so the mockup takes its screen height from sample values: 390 × 844, 1280 × 800 and 2200 × 1238. These are not device sizes. The two-page Duo is a sample shape, drawn 800 wide (two 390 pages and a 20px hinge), because `layout.json` gives the Duo no size. Fonts fall back offline; every mockup block has a fixed height, so no size below hangs on a font. Sizes are the picture box with its 1px border, as `getBoundingClientRect` gives them.

## 1. What filling the card buys

| Size | Card | Column | Phone picture today | Phone picture new | Gain |
|---|---|---|---|---|---|
| 390 (one option per row) | 319 | 289 | 224 × 480 | 289 × 622, whole | 1.29 x |
| 1280 and 2200, two per row | 397.5 | 367.5 | 224 × 480 | 367 × 790, whole | 1.64 x |
| 1280 and 2200, three per row | 261.7 | 231.7 | 224 × 480 | 231 × 496, whole | 1.03 x |

- Three options per row gain 3%. The card is the limit there, not the 480 cap: the page is at most 1160 wide on any screen, the rail takes 240, and three cards share 805. So on a 2200 screen the pictures stay as small as at 1280. See item 6.
- A two-page Duo picture already fills its card today: 367 × 386 at two per row, 231 × 242 at three, 289 × 303 at 390. It does not change.

## 2. The scale

`sc = min(2, W / w)`, where W = floor(column width) − 2 and w is the mockup's drawn width, or the focus box's width. So the picture is the card's width, unless that needs more than 2x (item 4). Today: `sc = min(1, W / w, max(480 / h, 120 / w))`.

## 3. The height rule. Pick: Grow to a phone

Each rule fills the card's width. They differ in what a tall picture does. Numbers: sample screens above; "visible" is the screen less the 56px header and the 96px send bar (704 at 390, 660 at 1280, 1098 at 2200).

1. **Grow to a phone (pick).** A picture draws whole while it is no taller than a 390 × 844 phone picture at the card's width: F = max(480, ceil(W × 844 / 390)). A taller one scrolls in today's 480 box, at the card's width less the scrollbar gutter.
   - Gain: every phone picture and every Duo picture draws whole, at the card's width, on every screen. A taller one scrolls in the box that waiting-page change c204 tested, so the share of the screen that a drag scrolls stays as today: 0.68 at 390, 0.73 at 1280, 0.44 at 2200. It reads no screen height, so a window resize moves nothing.
   - Loss: at two per row a phone picture is 790 high. On a 1280 × 800 screen (660 visible) its foot and the card's text below it need a page scroll. Height jumps at the threshold: a phone shape draws 790 high, a slightly taller page draws a 480 box beside it (case `two-tall`: 367 × 790 beside 367 × 480).
   - Loss: a picture scrolls sooner. Today it scrolls only past about 4:1 (c204 item 1); now past a phone's 2.16:1. A 390 × 1300 focus drew whole today at 146 × 480; now it scrolls in a 480 box at the card's width (231 × 480 at three per row, 289 × 480 at 390).
2. **Grow to the screen.** Whole up to the screen cap, max(480, screen − 56 − 96 − 32): 672 at 390, 628 at 1280, 1066 at 2200. Taller scrolls in a box that high.
   - Gain: no picture passes the screen.
   - Loss: on a 1280 × 800 screen a two-per-row phone scrolls in a 628 box. The box covers 0.95 of the visible area (0.97 at 2200), so a drag almost anywhere scrolls the picture, not the page. The size hangs on the window height, so the builder needs an `svh` probe and a refit on height change.
3. **Grow with no cap.** Never scrolls.
   - Gain: the c204 scroll box, cue and keys are never used.
   - Loss: a 390 × 2400 page draws 231 × 1410 at three per row, and pushes the gain and lose rows of all three cards down by 930px (their `.head` moves from 555 to 1485 below the card top). At 390 it is 289 × 1767; at two per row, 2247 high (computed).
4. **Keep the 480 box.** Whole up to 480; taller scrolls in 480.
   - Gain: no card row grows past today's height.
   - Loss: every phone picture at 390 and at two per row scrolls (289 × 480, 367 × 480), so the owner never sees one whole on the card.
5. **Shrink to the screen.** Today's rule with the screen cap: a picture past the cap shrinks to fit it, down to a phone's width.
   - Gain: every phone picture shows whole within the screen.
   - Loss: it breaks the goal. At two per row on 1280 × 800 a phone draws 293 × 628 in a 367 column, and a tall focus draws 191 × 628 in a 231 column.

Each rule has a Hide control in the mockup. The `pic-` states are one static figure per rule, for the waiting page (item 9).

## 4. Upscale. Pick: up to 2x, as the viewer

A focus box narrower than the card scales up until it fills, at most 2x (`stageFrame` already uses 2).
- Gain: a small focus fills the card. The sample 180 × 120 button pair draws 231 × 153 at three per row and 289 × 192 at 390, in place of 182 × 120. The frame draws vector text, so it stays sharp.
- Loss: a 1x mockup detail looks larger than it does on the device. Not picked: 1x (`up=1`), where the small focus stays 182 × 120, centred.

## 5. Measured sizes, pick (Grow to a phone, up to 2x)

Light and dark give the same sizes in all 123 pairs. In every run, View is 44 high. The picture's button (`.opic`, picture plus View) is at least 44 × 44 (smallest: 289 × 214). The picture is inside its card and column, and ends above `.head`. The page has no sideways scroll.

| Case | 390 | 1280 | 2200 |
|---|---|---|---|
| Three phones | 289 × 622 each, whole (today 224 × 480) | 231 × 496, whole | 231 × 496, whole |
| Two phones | 289 × 622, whole | 367 × 790, whole | 367 × 790, whole |
| Two-page Duo | 289 × 303 (as today) | 367 × 386 (as today) | 367 × 386 |
| Focus 390 × 220 | 289 × 162 (as today) | 231 × 130 | 231 × 130 |
| Focus 180 × 120 | 289 × 192 (today 182 × 120) | 231 × 153 | 231 × 153 |
| Focus 390 × 1300 | 289 × 480, scrolls (today 146 × 480 whole) | 231 × 480, scrolls | 231 × 480, scrolls |
| Page 390 × 2400, three per row | 289 × 480, scrolls (today 234 × 480) | 231 × 480, scrolls (as today) | 231 × 480, scrolls |
| Page 390 × 2400 beside a phone, two per row | 289 × 480 and 289 × 622 | 367 × 480, scrolls (today 234 × 480), beside 367 × 790 | as 1280 |

- At 1280 and 2200 the picture row of a three-option card grows by 16px (`.head` from 555 to 571 below the card top); of a two-option card by 310px (555 to 865).
- The scrollbar gutter measured 10px (`scrollbar-width: thin`). A scrolling box, as the table measures it, is the column wide: 289 at 390. Its picture draws the column less 12 (the 1px border on each side and the gutter): 277 wide at 390.
- The checks were computed again in the measure script, apart from the mockup's code. Each went red on a broken copy: a box 3px too wide (red for width and for "outside column") and a box 40px too short.

## 6. Card width: the limit at three per row and on wide screens

Owner grant: yes. Not drawn, and outside this lane. Filling the card does little at three per row (231 wide), and a 2200 screen shows the same 1160px page as 1280. Two ways to give pictures more room, for the owner to rule on:
- A wider page for an item with pictures on a wide screen, such as `.in` max-width 1600 at 1700px and wider.
- At most two options per row for an item with pictures (`.opts.pics`), so each phone picture draws 367 wide.

## 7. Ruling and what it replaces

- Ruling: owner pick a for waiting-page item 470 (the picture-size question), "a for 470", 2026-11-09 21:26 CST: Grow to a phone (section 3, rule 1). It fills the card, which is option B of waiting-page change c193 item 3, and sets the height rule. Not blocking.
- The pick replaces:
  - waiting-page change c193 item 3, option a (the 480 cap).
  - waiting-page change c204 item 6 (the scale in the scroll case; the 5B ruling, owner 2026-10-30 14:45 CDT, waiting item 84 pick b, scroll width 221.8). Now the picture draws the card's width less the 2px border and the gutter.
  - waiting-page change c204 item 1 (when a picture scrolls). It scrolled only past about 4:1. Now it scrolls past a phone's 2.16:1.
- Departs from: `optPic`'s maxScale 1 in today's code (waiting-page change c193 item 3 scope sets 2). Owner grant: yes, for section 4 (upscale). Not blocking.

## 8. Builder rules

- Change only `optPic`'s call and `fitFrame`'s capped path (`maxH`). `designPreview` (maxScale 1, no maxH) and the viewer's `stageFrame` (maxScale 2) do not change. The c204 scroll case keeps its DOM, cue, shades, gutter click cancel, keys, `inert` frame and `aria-hidden` wrap.
- `optPic` passes maxScale 2. In `fit()` with maxH: room0 = floor(column rect width) − 2; sc = min(maxScale, room0 / bw); F = max(maxH, ceil(room0 × PHONE_H / FIT_W)); scroll when ceil(bh × sc) > F + 1.
- Scroll case: turn `.scroll` on, read g as today, room = floor(column) − 2 − g, sc = min(maxScale, room / bw), box maxH high and pw + 2 + g wide. If then ceil(bh × sc) ≤ maxH + 1, the gutter made it fit: turn `.scroll` off, set g to 0, and draw it whole at this narrowed sc (width = room). Its height is then at most maxH + 1, which is within F + 1.
- `MIN_PIC` stays as a number (check_designs.mjs and the write guard read it); fitFrame stops using it as a width floor. `PHONE_H` stays, in F. The 5B width cap min(221.8, …) goes.
- In both branches, the measured one and the declared-size one, set the width and height from the column, so the first paint already has the size.
- The c204 acceptance check ("a picture that fits looks as today") turns false by design. Re-point it: a picture that fits is floor(column) wide, or 2 × its width when that is less.
- The sizing rule's home is `reference/designs.md` (skill `waiting-page`), section "Add a design": step 1, and the `focus` bullet of step 4."

## 9. Card pictures for the waiting page

Each `pic-` state draws one figure, 300 wide, with its `data-state` and `id` in the static markup. Each draws two cards at 1280, two per row, on a 1280 × 800 screen at 0.3 scale: a phone picture and a very tall one, with the screen's edge. The five figures differ (pixel compare, light and dark).

| Option | `state` | `focus` | `size` |
|---|---|---|---|
| Grow to a phone | `pic-phone` | `#pic-phone` | {w: 300, h: 457} |
| Grow to the screen | `pic-screen` | `#pic-screen` | {w: 300, h: 457} |
| Grow with no cap | `pic-grow` | `#pic-grow` | {w: 300, h: 457} |
| Keep the 480 box | `pic-box` | `#pic-box` | {w: 300, h: 457} |
| Shrink to the screen | `pic-shrink` | `#pic-shrink` | {w: 300, h: 457} |
| Today (main's rule: 480 cap, maxScale 1, a tall picture 221.8 wide) | `pic-today` | `#pic-today` | {w: 300, h: 457} |

`pic-today` draws the same two sample pictures as `pic-grow`, so the two can sit side by side as options. Today, two per row at 1280: phone 224 × 480 whole, very tall 234 × 480 scrolls.

## 10. Deep links

`#s=three-phone|two-phone|duo|focus|tall|two-tall|pic-phone|pic-screen|pic-grow|pic-box|pic-shrink|pic-today`, `&r=today|phone|screen|grow|box|shrink`, `&up=2|1`, `&w=all|390|1280|2200`, `&t=light|dark`, `&lab=off`, `&hide=<ids>`.
