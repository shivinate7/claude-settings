# Waiting page c204: a tall option picture scrolls in its box

Mockup: `c204-scroll.html`. It puts only its changes in `#newcss`, with today's value in a comment. Screen: `skills/waiting-page/page.html` at 1cc47f01 (`optPic`, `fitFrame`, `MIN_PIC`, `.dfitwrap`, `.opt .opic`). Owner's word: waiting-page item 55 note, Oct 28 17:50 CDT. The mockup was measured with headless Chromium 153 at 390, 1280 and 2200, light and dark, and at 1065 (the narrowest page with three option columns). Fonts fall back offline.

1. When a picture scrolls. The scale does not change: sc = min(1, W / w, max(480 / h, 120 / w)), where w × h is the mockup (390 wide) or the focus box. The picture scrolls only when ceil(h × sc) > 480. That is a box more than 4 times as tall as it is wide, such as a 390-wide mockup taller than 1560px. A focus box under 120 wide and over 480 high also scrolls. Every other picture draws as today: the same width, height and transform. The mockup measured this in each fit case.
2. Question 1, a focused card (1A, pick). The card scrolls only over the focus box, and opens at the top of the box.
   - Gain: this keeps today's rule. The card shows only the focus element (`SKILL.md` "Waiting page" section, `focus`; `fitFrame` translates by −box). The open position is scrollTop 0, so no timing can make it wrong. A focus that fits is unchanged.
   - Loss: the mockup above and below the focus is still only in View.
   - 1B (state `focus-whole`, "Hide 1B" removes it): scroll the whole mockup in the focus column, and open with the focus at the top (scrollTop = round(box.y × sc)). Gain: the context round the focus is in the card. Loss: the open position needs the box that the frame posts, so a cached or declared first paint opens in the wrong place. A focus narrower than the mockup cuts the columns at its sides. Departs from: `SKILL.md` "the option card then shows that element whole", and the `fitFrame` focus translate. Owner grant: yes, only if the owner wants 1B. Not blocking.
3. Question 2, the open position and the cue.
   - Open position: the top of what the card shows. That is the top of the mockup with no focus, and the top of the focus box with a focus.
   - Cue: a pill, "↓ More", centred 8px above the bottom edge. It is 24px high with padding 0 8, radius 12, and 600 12px text. Its colours are `--pic-cue` #161b22 and `--on-pic-cue` #ffffff, with a 1px ring in `--on-pic-cue`. It sits on a 40px shade, rgb(22 27 34 / 0.28) at the bottom edge.
   - A 12px shade at the top edge shows once the picture is scrolled. The cue goes when the picture reaches its end (scrollTop + clientHeight ≥ scrollHeight − 1).
   - Contrast, measured: the pill on the frame is 17.9:1, and the text on the pill is 17.9:1. The frame is #fff in both themes, so the values hold in light and in dark. The cue never sits on `--surface`.
   - The cue and the shades are sticky overlays whose net height is 0, so they move nothing. Their opacity fades in 150ms linear, only under `prefers-reduced-motion: no-preference`.
   - Why not the scrollbar alone: overlay scrollbars on iOS, Android and macOS hide when idle.
4. Question 3, tap or scroll on a phone. The frame stays inert (pointer-events none). A drag on the picture scrolls the box, and a tap opens View, as today.
   - Keep the default `overscroll-behavior`. At the picture's end, a drag or a wheel moves the page.
   - Loss: the page scroll pauses while the picture under the finger or the wheel scrolls.
   - A press on the scrollbar fires `click` on `.opic`. The mockup measured this for both the thumb and the track. So `open()` ignores a press whose clientX is past the wrap's left + clientLeft + clientWidth. Measured: a press on the gutter opened View 0 times, and a press on the picture opened it 1 time.
   - Tap opens View, measured with touch. A touch drag that scrolls is unmeasured: in this headless build, a synthesized touch scroll did not move a plain control scroller either.
5. Question 4, the keyboard path. `.opic` stays the one tab stop of the picture. The View sheet stays the keyboard route to the whole mockup.
   - While `.opic` has focus, ArrowUp and ArrowDown scroll 40px, and PageUp and PageDown scroll clientHeight − 40. Home and End go to the ends. Call preventDefault only when scrollTop changed, so at an end the page scrolls. Enter and Space still open View. Measured: ArrowDown twice moved 80px.
   - In the scroll case, the aria-label adds ". Arrow keys scroll its picture".
   - The wrap gets tabindex −1 and `aria-hidden="true"`. The card's iframe gets tabindex −1.
   - Why: Chromium makes a scroller with no focusable child a tab stop (measured). A tab stop in a `role=button` is an axe `nested-interactive` violation. With tabindex −1, axe reports `scrollable-region-focusable` (measured). With `aria-hidden` added, axe reports nothing (measured). `aria-hidden` is true to the content: a button's children are presentational, its label names the option, and View holds the same mockup.
   - Today the inert card iframe is a tab stop inside the button. Measured tab order: radio, picture, the frame, the next control. tabindex −1 removes that extra stop. Departs from: today's tab order. This is a fix, so no grant is needed.
6. The scale in the scroll case.
   - 5A (build this): keep today's scale. The picture is min(w, 120) wide, so a 390 mockup draws 120 wide and the box is 132 × 480 (120 + 10 gutter + 2 border).
   - 5B (state `wide`, "Hide 5B" removes it): draw the width of a 390 × 844 phone picture, min(221.8, column − 2 − gutter). Measured: 222 at 390, 219 at 1280 and 2200, and 188 at 1065. Gain: the picture is as wide as the phone pictures beside it, and its text is 1.85 times larger. Loss: the width jumps at the threshold. A 1550px mockup draws 120.8 × 480 whole, and a 1570px mockup draws 221.8 wide and scrolls.
   - Departs from: `fitFrame`'s scale and `MIN_PIC` in the scroll case. Owner grant: yes. My recommendation is 5B. Not blocking: the builder builds 5A, and 5B is a change to the scale line only.
7. Builder rules.
   - The change applies only to `optPic`'s call (maxH 480). `designPreview` and `stageFrame` do not change.
   - DOM of a capped wrap: wrap > `.dtop`, `.dsizer` > iframe, `.dcue` > `.dmore`. `.dsizer` is display block, position relative, overflow hidden, and pw × ceil(bh × sc), where bh is the focus box height, else the mockup height. The iframe keeps today's position and transform inside the sizer.
   - Why a sizer: a scroller's range starts at 0, so scroll overflow cannot reach negative translate coordinates. The scroll case needs a sized inner box plus scrollTop. Also, a transformed iframe adds its whole box to the scroll range unless a box with overflow hidden clips it. With 1B, the sizer is ceil(ht × sc) high, and only x is translated.
   - In `fit()`, compute sc as today, then set scroll = ceil(bh × sc) > maxH, and toggle `.scroll`. In the scroll case, read g = wrap.offsetWidth − wrap.clientWidth − 2 after `.scroll` is on. Set the wrap to (pw + 2 + g) × maxH. Do this in both branches, the measured one and the declared-size one, so the first paint is already 480 high. The declared branch then sets the height and no aspect-ratio.
   - With 5B, the width budget is floor(column rect width) − 2 − g. A rounded clientWidth let the box pass the column by 0.17px.
   - Set the first scrollTop once per wrap, never inside `fit()`, because `fit()` runs on every resize, message and repaint. With 1A, the first scrollTop is 0, so there is nothing to set. With 1B, set it after the first fit with a measured box (in the message handler), behind a per-wrap flag. When the person has scrolled, skip it.
   - The repaint merge in `syncOpts()` swaps only `.view` and keeps the wrap, so the scroll position survives a repaint. The builder confirms this.
   - A passive scroll listener on the wrap toggles `.scrolled` and `.at-end`. Call it once after each fit too.
   - The gutter: `.dfitwrap.scroll` has `scrollbar-width: thin` and `scrollbar-gutter: stable`. Headless Chromium draws a default scrollbar as an overlay (0px, measured). With `thin`, it draws a 10px classic gutter, so the measurements cover the classic case.
8. Fixed sizes kept: the 480 cap, the 120 floor, 32px chips, and the 44px View bar. The page has no sideways scroll.
9. Measured verdicts. Each state was measured at each size, light and dark: `long`, `long-end`, `focus-in`, `focus-whole`, `fits`, `keys` and `wide`. Checks per picture: at most 480 high, inside its card and column, and above `.head`. Scroll case: 480 high, picture width = content width (the gutter takes none of it), no sideways scroll, opens at the right place, cue shown before the end and hidden at it, not a tab stop. Fit case: the size equals today's formula. Page: scrollWidth = clientWidth. A copy with the gutter left out of the width failed these checks, so they catch that defect.

   | Size | Light | Dark |
   |---|---|---|
   | 390 | pass | pass |
   | 1065 | pass | pass |
   | 1280 | pass | pass |
   | 2200 | pass | pass |

   - Sizes: scroll box 132 × 480 at every width (5A). Fit pictures as today: phone 224 × 480. Folded focus: 289 × 310 at 390, 232 × 248 at 1280 and 2200, and 200 × 214 at 1065. Tall focus that fits: 146 × 480.
   - axe (wcag2a to wcag22aa) on `long` and `focus-in`: 0 violations for this change. It reported two others. `document-title` comes from the harness frame. `aria-prohibited-attr` on `.spark` is in today's page.html `sparkle()`: an aria-label on a `<b>` with no role. That is outside this lane.
   - Today's fit picture at full column width passes its column by 0.17px on each side. It is sub-pixel and inside the card padding. This change leaves it as it is.
