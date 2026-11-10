# Waiting page c193: sizes for the builder

Mockups: `c193-receipt.html`, `c193-rail.html`, `c193-pics.html`, `c193-sent.html`. Each mockup puts only its changes in `#newcss`, with today's value in a comment. Screen: `skills/waiting-page/page.html` at 2628ab37. Steps come from `tokens.md`: 4 = `--space-1`, 8 = `--space-2`, 12 = `--space-3`, 16 = `--space-4`. The mockups were measured with headless Chromium at 390, 1280 and 2200, light and dark. Fonts fall back offline, so a height that depends on text is approximate.

1. Receipt (`receipt()`, `patch()`, `releaseSent()`, `heldWatch`). A card the owner sends drops to its content at once, and a scroll correction keeps the first card in the reading band where it was. A card that turns into a receipt otherwise keeps the open card's height while any part of it is in view: 615px at 1280 and 2200, 982px at 390. Wholly off screen, it shrinks to its content: filed 205px and pending 212px at 1280; filed 286px and pending 331px at 390. `.receipt` gap 8 (today 10). `.line` becomes a grid: `12px minmax(0,1fr) auto`, gap 4/8, min-height 44. "Read by" goes under the choice, and Change spans both rows. `.ans`: min-height 24, padding 0 8, flex-wrap, so the time wraps whole at 390. Gain: at 390, today's flex row puts each part on its own line, and the grid stops that. Loss: none measured. Pick: grid.
2. Rail at 961px and wider (`renderRail`). The content box is 240 − 32 − 2 = 206px.
   - Chips: 206 × 32 (today 30), gap 4, padding-inline 8. `.no` has min-width 2ch and tabular-nums. `.nt` ends in an ellipsis; the mockup measured scrollWidth > clientWidth.
   - Dashed frame: 206 wide, padding 4, gap 4, radius 12 (today 2, 3, 10). Chips inside are 196 × 32.
   - At 960px and narrower: a chip is 48 × 32 inside and outside a frame (today 44 × 28 inside).
3. Option pictures (`optPic`, `fitFrame`). Scale: sc = min(2, W / w), where W = floor(column) − 2 and w is the mockup's width (390) or the focus box's width. `.opic` is a grid with gap 8. View is 44px high (today 40).
   - In the 1160px column: `.in` content is 1128, the list is 860, and the options row is 805. Three options are 261.7px wide each and two are 397.5px. The picture sizes are in the picture notes, section 5 (decision `page-pic-fills-card`, an option picture fills its card). At 2200 the sizes are the same as at 1280.
   - At 390: the option card is 319px wide. Its picture size is in the picture notes, section 5.
   - Narrowest case: three options reach three columns at a 1065px page. The cards are then 230px wide. The picture size there is unknown: the picture notes do not measure 1065.
   - Scope: `optPic`'s call only (maxScale 2, maxH 480). The viewer (`stageFrame`, maxScale 2) and the front preview (`designPreview`) are unchanged.
   - In `fit()`, set the wrap's width to the picture's width plus its border in JS, and CSS centres it (`justify-self: center`). A box out of the page, or in a hidden part of it, has no column yet: it takes the picture's drawn width and stays pending. `render()` places a pending box once its card is in the page, in the same task, so the first frame is the placed size. Decision `page-pic-fills-card` (docs/decisions/page-pic-fills-card.md).
   - The mockup checks that each picture stays inside its card and ends above `.head`.
   - The picture fills the card's width, at most 2x. It draws whole while its drawn height is at most F + 1, where F = max(480, ceil(W × 844 / 390)). Taller, it draws 480 high and scrolls. Rule: decision `page-pic-fills-card`, owner 2026-11-09 21:26 CST.
4. Sent bar (`renderSent`). Move `.sent-list` into a new `.sent-what` block, under the sent line.
   - `.sent .in`: flex-wrap, padding-block 16, gap 12/16. `.sent-head` gap 16. `.sent-what` gap 8. `.sent-list` gap 8. Each `li` is 28 high with padding-inline 12. `.row` gap 8, margin-inline-start auto.
   - Bar `.in`: padding-block 12, gap 8/12 (today 10, 8/10).
   - Close keeps its x when Undo goes (measured). `#undoBtn` uses tabular-nums.
   - Stamp: 48px high, the same as Send. Border 2, padding 4 8, "SENT" 700 18/20, time 500 12/16 mono, rotate −4deg.
   - Motion: `stamp-settle 200ms cubic-bezier(0.2, 0, 0, 1) both`, opacity 0 → 1 and scale 1.06 → 1. Every y value is in [0, 1], so it has no overshoot. Today: .42s, from scale(2), y1 1.6. Keep the `prefers-reduced-motion: no-preference` guard, so that with reduced motion the stamp shows still. Per `tokens.md`, motion values belong to this repo.
5. Departs from: at 960px and narrower, rail chips stay 32px high. That is under the 44px touch floor in `a11y.md` (today's behaviour). Owner grant: yes, to make them 44px. Each chip row on the phone rail would grow by 12px. Not blocking.
