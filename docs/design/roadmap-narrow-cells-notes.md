# Roadmap Plan view: paused and stalled cells in narrow bars, design notes

Mockup: `roadmap-narrow-cells.html`. The page CSS in the mockup is `skills/roadmap/page/index.html` at 6a985d93d
(the branch of PR #1635, stalled steps in red), both style blocks, unchanged. Option CSS goes after it. Sizes: Phone 390
and Wide 1280, the brief's sizes; this repo's device list reads "unknown". Themes: light and dark. Data: the test
fixture `barFixtureBlocked` with `STALLED_S3_P4` (30 steps: 1 done, 1 in progress, 1 stalled, 1 paused, 1 blocked, 25
to do), and a 12-step phase.

Deep links: `#s=fixture|wide`, `&pz=low|ring|today`, `&nr=runs|count|today`, `&w=all|390|1280`, `&t=light|dark`,
`&lab=off`, `&hide=pz:ring,nr:count` (one hide button per option). Focus ids: `pick-bars` (phase head bar, the paused
cue), `pick-rail` (the 30-step rail chip, the narrow rule). The list under each frame is read from the drawn frame:
bar width, cells or runs, the narrowest drawn part, the paused mark, and the token contrasts.

Measured today (the mockup's "Today" options, 30 steps): rail chip 58px at 390 (cells 0px, nothing drawn), rail chip
97px at 1280 (1.3px), phase head 90px at 1280 (1.06px). The 97px is the mockup's layout, not the page's: the shipped
rail chip at 1280 is 216.8px (5 equal columns, 7.2px a cell), so it draws cells. There a paused ring fills its cell and paints solid
`--muted` beside a solid `--accent` done cell: 1.08 to 1.25:1. Now card and phase head at 390 are 5px a cell or more.

## Items

1. **Narrow rule, option Runs.** A bar draws one cell per step while each cell gets 3px or more beside 2px gaps: bar
   width at least steps x 5px - 2px. Under that, it draws one block per kind (done, in progress, stalled, paused,
   blocked, to do), 2px apart, each as wide as its share of steps and never under 4px.
   Gain: every drawn part is 4px or wider, so each kind keeps its shape. The 58px chip draws a bar again. The cells stay
   in the DOM at 0 width, so the cell-order tests still read 30 cells.
   Loss: a narrow bar no longer counts steps; the d/n count and the bar's name do. A 1-step block at its 4px floor
   reads larger than its share (4px of 58px for 1 of 30).
   Departs from: `skills/roadmap/page/index.html` `segs` and `.bar`, one cell per step at every width.
   Owner grant: yes. Pick: yes.

2. **Narrow rule, option Count only.** The same threshold. Under it, no bar: the chip's d/n count stays.
   Gain: no proportion shown wrong. Loss: the 30-step chip and the phase head at 1280 draw no bar while the other chips
   do, and stalled and paused leave no mark there. Pick: no.

3. **Narrow rule, Today.** One cell per step with 2px gaps. Shown so the owner can compare. Pick: no.

4. **Paused cue, option Low cell.** A paused cell paints only its lower half, in `--muted`, at every width. The empty
   top half and the gaps beside it leave a notch in the bar's top edge.
   Gain: the cue is shape, not colour, so it holds when `--muted` and `--accent` are near each other (1.08 to 1.25:1).
   It reads against the card's `--surface` (5.09:1 light, 6.35:1 dark). One rule at every width.
   Loss: the ring that echoed the pause mark is gone.
   Departs from: `.bar i.pzd` (the ring), the pick in `roadmap-stalled-paused-notes.md` item 2.
   Owner grant: yes. Pick: yes.

5. **Paused cue, option Ring, low when narrow.** Today's ring at 5px and wider (`::before`), the low half under 5px
   (`::after`). Gain: keeps the ring where it has a hollow. Loss: two shapes for one state, and two pseudo-elements.
   Pick: no.

6. **Paused cue, Today: ring.** Shown so the owner can compare. Pick: no.

7. **Stalled hatch, checked.** At 1.06px today the stripes break into a red stub and a gap. Under Runs a stalled block
   is 4px or wider and shows at least one whole stripe and one gap, light and dark. No change.

## Builder changes, `skills/roadmap/page/index.html` (picks 1 and 4)

- CSS: `.bar{position:relative}` added to `.bar`.
- CSS: `.bar>i{max-width:clamp(0px,calc((100% - var(--n)*5px + 2.01px)*1000000),100%)}`.
- CSS: `.bar>.runs{display:flex;position:absolute;top:0;bottom:0;left:0;gap:2px;overflow:hidden;width:clamp(0px,calc((var(--n)*5px - 2px - 100%)*1000000),100%)}`.
- CSS: `.bar>.runs>i{flex:var(--c) 1 0px;min-width:min(4px,calc((100% - var(--k)*2px + 2px)/var(--k)));height:100%}`.
- The switch is a step at W = 5px x steps - 2px: at or above it the cells draw (the 0.01px lead keeps them on at W = edge),
  below it the runs layer is the full bar (the layout grid is 1/64px, so one step under makes the product 15625px or more).
  A x1000 factor left the runs layer (edge - W) x 1000px wide, and 0 at the edge, so nothing drew there.
- JS: `<b class="runs">` gets `style="--k:K"`, its run count (at least 1).
- CSS: `.bar i.pzd{background:linear-gradient(var(--muted),var(--muted)) left bottom/100% 50% no-repeat;box-shadow:none}`, in place of the ring.
- JS: `segs(c,n)` appends `<b class="runs">` holding one `<i class="KIND" style="--c:COUNT">` per kind with a count above 0, in
  the cell order, then `<i style="--c:TODO">`.
- JS: each bar gets `--n`, its step count (at least 1): `renderNow` (merged with its `margin-top:7px`), `renderRail`, and
  the phase head bar in `renderPhase`.
- Cost: one absolutely placed layer of at most 6 elements per bar. No ResizeObserver and no layout read: the switch is
  the `clamp(... * 1000000)` step switch, the same text on the waiting page.

## Test check (geometry and tokens, not painted pixels)

With `barFixtureBlocked` and `STALLED_S3_P4`, at 390 and 1280, light and dark, for the Now card, the cleanup rail chip
and the phase head bar:
- Exactly one layer draws: the widest `.bar > i` is over 0px, or `.bar > .runs` is over 0px wide, never both.
- Every drawn part (the cells, or `.runs > i`) is at least 3px wide.
- At 5 x steps - 3, - 2.02, - 2 and - 1 px (30 and 13 steps) exactly one layer draws and it spans the bar.
- In runs mode, the run classes read `["done","act","stl","pzd","blk",""]`.
- The 58px chip at 390 and the 90px phase head at 1280 are in runs mode; the Now card is in cell mode.
- The paused part has `background-size` `100% 50%`, `background-position` `0% 100%`, and `box-shadow` `none`.
- `--muted` and `--bad`, read from the computed `:root`, each reach 3:1 against `--surface`.
- The cell-order tests read `.bar > i`, so they keep their 30 cells and need no change.
- Re-point: `barActCells` in `skills/roadmap/tests/page.test.mjs` counts `.bar i.act`, a descendant selector, so it
  would also count the in-progress run. Make it `.bar > i.act`.

## Critique (impeccable, single context)

Degraded: single context, no sub-agent tool in a designer, and the context launcher is refused here. The detector found
nothing in either mockup; it reads the harness, not the screen in the frames.
- Open: one screen can show one phase two ways. At 390 the Now card draws 30 cells while the rail chip draws runs. CSS
  cannot make one bar follow another's width. A question for the owner, not blocking: is that acceptable, or should a
  phase that goes to runs in any bar go to runs in all of them (JS, one layout read per render)?
- Open: nothing on the screen teaches that a low cell means paused, as nothing taught the ring. The bar's `title` and
  the Now card words carry it.
- The 4px floor of a run holds for every bar the pages draw. The narrowest is the 30-step rail chip, 39.4px at a 320px
  viewport; k runs need 6k - 2px (34px for six, the most there are). Below 6k - 2px the floor gives way: each run takes
  an equal share, so every run stays visible. The test pins only that each run shows at 1px or more (a 6-step bar, 20px).
- Open: at the 4px floor a 1-step run reads larger than its share (4px of 58px for 1 of 30). The d/n count is exact.
- Fixed: none needed in the bars. The harness labels sit below the bars, so they cover no cell.

## Seen, outside this lane

- In forced-colors mode the bar cells lose their backgrounds, stripes and low half, as every cell does today.
- The mockup leaves the side column empty at 1280; only the bars change.
