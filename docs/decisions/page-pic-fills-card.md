# An option picture fills its card and grows to a phone

## The ruling

- Ruling: owner pick a, "Grow to a phone", on waiting-page item 470 (the picture-size question), 2026-11-09 21:26 CST.
- Opened by: owner, 2026-11-09 20:47 CST, "the images are so small in the artifact cockpit" (the owner's page ask, id ask-mwa3hdpa1j).
- Width: the picture fills its card's width. Its scale is at most 2x: `sc = min(2, W / w)`. Here W = floor(column width) − 2, and w is the mockup's width or the focus box's width.
- Whole: a picture draws whole while its drawn height is at most F + 1, where F = max(480, ceil(W × 844 / 390)). F is the taller of 480 and a 390 × 844 phone picture at the card's width. The 1 px is the code's tolerance: a picture 1 px over F still draws whole.
- Tall: a picture taller than F + 1 draws 480 high and scrolls. It is as wide as the card, less the scrollbar gutter.
- Gutter edge: a picture that would scroll only because the scrollbar gutter takes width draws whole at the narrower scale (width = card less gutter), with no scroll. Its height is then at most 481, which is within F + 1.
- First paint: the box's first painted frame equals its settled height. Its width and height come from the column before the picture draws, and from the declared height until the mockup reports its own.
- Unchanged: the viewer (`stageFrame`) and the front preview (`designPreview`).
- Kept: `MIN_PIC` stays in the page. The write check, `check_designs.mjs`, reads it.
- Still holds: waiting-page change c204, items 2 to 5 (the focus card, the cue, the touch split and the keys).
- Departs from: waiting-page change c193, item 3, option A (the 480 cap). Waiting-page change c204, item 6 (ruling 5B, owner 2026-10-30 14:45 CDT, waiting item 84 pick b: scroll width 221.8). Waiting-page change c204, item 1 (a picture scrolls only past about 4:1).

## Trade-offs

Sizes are measured in the picture notes, section 5. The costs of pick a are in section 3, rule 1.

- Gain: every phone picture and every Duo picture draws whole at the card's width, on every screen. The rule reads no screen height, so a window resize moves nothing.
- Loss: at two options per row a phone picture is 790 high. On a 1280 × 800 screen, its foot and the card text below need a page scroll.
- Loss: the height jumps at the threshold. A phone shape draws 790 high, and a page a little taller draws a 480 box beside it.
- Loss: a picture scrolls sooner. It now scrolls past a phone's 2.16:1, not about 4:1.

## Not picked

Section 3, rules 2 to 5: grow to the screen, grow with no cap, keep the 480 box, and shrink to the screen.

## Known limit

- At three options per row, the picture is 231 × 496 at 1280 and 2200. It was 221.8 × 480 (c193 item 3). So filling gains about 4% in width and 3% in height there.
- A wider page for pictured items is not decided.

Kind: build
Plan: docs/decisions/page-pic-fills-card.md#the-ruling (all)
Home: skills/waiting-page/page.html
