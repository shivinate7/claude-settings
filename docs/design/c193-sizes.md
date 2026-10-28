# Waiting page c193: sizes for the builder

Mockups: `c193-receipt.html`, `c193-rail.html`, `c193-pics.html`, `c193-sent.html`. Each mockup puts only its changes in `#newcss`, with today's value in a comment. Screen: `skills/waiting-page/page.html` at 2628ab37. Steps come from `tokens.md`: 4 = `--space-1`, 8 = `--space-2`, 12 = `--space-3`, 16 = `--space-4`. The mockups were measured with headless Chromium at 390, 1280 and 2200, light and dark. Fonts fall back offline, so a height that depends on text is approximate.

1. Receipt (`receipt()`, `patch()`, `heldWatch`). While any part of the card is in view, a held card keeps the open card's height: 615px at 1280 and 2200, 982px at 390. When the card is wholly off screen, it shrinks to its content: filed 205px and pending 212px at 1280; filed 286px and pending 331px at 390. `.receipt` gap 8 (today 10). `.line` becomes a grid: `12px minmax(0,1fr) auto`, gap 4/8, min-height 44. "Read by" goes under the choice, and Change spans both rows. `.ans`: min-height 24, padding 0 8, flex-wrap, so the time wraps whole at 390. Gain: at 390, today's flex row puts each part on its own line, and the grid stops that. Loss: none measured. Pick: grid.
2. Rail at 961px and wider (`renderRail`). The content box is 240 − 32 − 2 = 206px.
   - Chips: 206 × 32 (today 30), gap 4, padding-inline 8. `.no` has min-width 2ch and tabular-nums. `.nt` ends in an ellipsis; the mockup measured scrollWidth > clientWidth.
   - Dashed frame: 206 wide, padding 4, gap 4, radius 12 (today 2, 3, 10). Chips inside are 196 × 32.
   - At 960px and narrower: a chip is 48 × 32 inside and outside a frame (today 44 × 28 inside).
3. Option pictures (`optPic`, `fitFrame`). Scale: sc = min(1, W / w, 480 / h), where w × h is 390 × 844 or the focus box. The picture is at most 221.8 × 480, centred. `.opic` is a grid with gap 8. View is 44px high (today 40).
   - In the 1160px column: `.in` content is 1128, the list is 860, and the options row is 805. Three options are 261.7px wide each and two are 397.5px. The picture is 221.8 × 480 in each. At 2200 the sizes are the same as at 1280.
   - At 390: the option card is 319px wide, and the picture is 221.8 × 480.
   - Narrowest case: three options reach three columns at a 1065px page. The cards are then 230px wide, and the picture is 200 × 433.
   - Scope: the cap applies only to `optPic`'s call (inert, maxScale 1). It does not apply to `designPreview` or to the viewer (`stageFrame`, maxScale 2).
   - In `fit()`, set the wrap's width to w × sc in JS and centre it. Do this in both branches, the measured one and the declared-size one, so the first paint already has the capped size.
   - The mockup checks that each picture stays inside its card and ends above `.head`.
   - Option A (pick): the 480px cap. Option B: the picture fills the card, at 231.7 × 501 (three options), 367.5 × 795 (two options) and 289 × 625 (at 390). B is easier to read, but two options are 800px high.
4. Sent bar (`renderSent`). Move `.sent-list` into a new `.sent-what` block, under the sent line.
   - `.sent .in`: flex-wrap, padding-block 16, gap 12/16. `.sent-head` gap 16. `.sent-what` gap 8. `.sent-list` gap 8. Each `li` is 28 high with padding-inline 12. `.row` gap 8, margin-inline-start auto.
   - Bar `.in`: padding-block 12, gap 8/12 (today 10, 8/10).
   - Close keeps its x when Undo goes (measured). `#undoBtn` uses tabular-nums.
   - Stamp: 48px high, the same as Send. Border 2, padding 4 8, "SENT" 700 18/20, time 500 12/16 mono, rotate −4deg.
   - Motion: `stamp-settle 200ms cubic-bezier(0.2, 0, 0, 1) both`, opacity 0 → 1 and scale 1.06 → 1. Every y value is in [0, 1], so it has no overshoot. Today: .42s, from scale(2), y1 1.6. Keep the `prefers-reduced-motion: no-preference` guard, so that with reduced motion the stamp shows still. Per `tokens.md`, motion values belong to this repo.
5. Departs from: at 960px and narrower, rail chips stay 32px high. That is under the 44px touch floor in `a11y.md` (today's behaviour). Owner grant: yes, to make them 44px. Each chip row on the phone rail would grow by 12px. Not blocking.
