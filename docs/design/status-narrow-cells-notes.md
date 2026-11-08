# Waiting page Status tab: paused and stalled cells in narrow bars, design notes

Mockup: `status-narrow-cells.html`. The page CSS in the mockup is `skills/waiting-page/page.html` at 6a985d93d (the
branch of PR #1635, stalled steps in red), unchanged. Option CSS goes after it. Sizes: Phone 390 and Wide 1280, the
brief's sizes; this repo's device list reads "unknown". Themes: light and dark. Data: the test fixture `barsBlockedPage`
(30 steps: 1 done, 2 in progress, 3 stalled, 1 paused, 1 blocked, 22 to do), and a 12-step phase.

Deep links: `#s=fixture|wide`, `&pz=low|ring|today`, `&nr=runs|count|today`, `&w=all|390|1280`, `&t=light|dark`,
`&lab=off`, `&hide=pz:ring,nr:count`. Focus ids: `pick-bars` (phase head bar, the paused cue), `pick-rail` (the 30-step
rail chip, the narrow rule). The list under each frame is read from the drawn frame.

Measured today (30 steps): rail chip 104.7px at 390 (1.55px a cell), phase head 110px at 1280 (1.72px). Every other
bar is 4.3px a cell or more. Today a paused cell under 3px paints solid `--ink` (light) or `--ground` (dark). That
reaches 3:1 against a done cell but sits near a to-do cell in shape: both are solid blocks. No solid colour reaches 3:1
against both done and to do, since done to to do is only 4.9 to 5.7:1.

## Items

1. **Narrow rule, option Runs.** One cell per step while each cell gets 3px or more beside 2px gaps (bar width at least
   steps x 5px - 2px). Under that, one block per kind, 2px apart, as wide as its share and never under 4px.
   Gain: every drawn part is 4px or wider. Both pages draw one bar. Cells stay in the DOM at 0 width, so the
   cell-order tests still read 30 cells.
   Loss: a narrow bar no longer counts steps; the d/n count and the `.sr` words do. A 1-step block at its 4px floor reads
   larger than its share.
   Departs from: `skills/waiting-page/page.html` `segs` and `.segbar`, one cell per step at every width.
   Owner grant: yes. Pick: yes.

2. **Narrow rule, option Count only.** The same threshold; under it, no bar, the d/n count stays.
   Loss: the current chip draws no bar while its neighbours do. Pick: no.

3. **Narrow rule, Today.** One cell per step with 2px gaps. Pick: no.

4. **Paused cue, option Low cell.** A paused cell paints only its lower half, in `--muted`, at every width. The empty top
   half and the gaps leave a notch in the bar's top edge.
   Gain: shape, not colour. In dark, `--acc` and `--muted` are 1.02:1 apart, and the paused block still reads apart from
   the done block by its height. `--muted` on `--surface` is 6.47:1 light, 7.37:1 dark.
   Loss: the ring is gone, and so is today's solid paint under 3px.
   Departs from: `.segbar i.pzd` (the ring) and `.segbar i.pzd::after` (the solid paint), the pick in
   `status-stalled-paused-notes.md` item 1. Owner grant: yes. Pick: yes.

5. **Paused cue, option Ring, low when narrow.** The ring at 5px and wider, the low half under 5px. At 1280 the Now card
   (4.34px a cell) and rail chip (4.69px) fall under 5px, so one screen shows both shapes. Pick: no.

6. **Paused cue, Today: ring, solid under 3px.** Pick: no.

7. **Stalled hatch, checked.** At 1.55 to 1.72px today the stripes break into a red stub and a gap. Under Runs the
   stalled block (3 steps) is 4px or wider and shows whole stripes, light and dark. No change.

## Builder changes, `skills/waiting-page/page.html` (picks 1 and 4)

- CSS: `.segbar` gets `position: relative`.
- CSS: `.segbar > i { max-width: clamp(0px, calc((100% - var(--n) * 5px + 2.5px) * 1000), 100%); }`.
- CSS: `.segbar > .runs { display: flex; position: absolute; top: 0; bottom: 0; left: 0; gap: 2px; overflow: hidden; width: clamp(0px, calc((var(--n) * 5px - 2.5px - 100%) * 1000), 100%); }`.
- CSS: `.segbar > .runs > i { flex: var(--c) 1 0px; min-width: 4px; }`.
- CSS: `.segbar i.pzd { background: linear-gradient(var(--muted), var(--muted)) left bottom / 100% 50% no-repeat; }`, in place
  of the ring. Delete `.segbar i.pzd::after` and its two dark-theme rules.
- JS: `segs(c, n)` appends `<b class="runs">` holding one `<i class="KIND" style="--c:COUNT">` per kind with a count above
  0, in the cell order, then `<i style="--c:TODO">`.
- JS: each `.segbar` gets `style="--n:N"` (at least 1): `renderNow`, `renderRail`, and the phase head.
- Cost: one absolutely placed layer of at most 6 elements per bar. No ResizeObserver and no layout read.

## Test check (geometry and tokens, not painted pixels)

With `barsBlockedPage`, at 390 and 1280, light and dark, for the three bars in `BARS_W`:
- Exactly one layer draws: the widest `.segbar > i` is over 0px, or `.segbar > .runs` is over 0px wide, never both.
- Every drawn part is at least 3px wide.
- In runs mode, the run classes read `["done","act","stl","pzd","blk",""]`.
- The cleanup rail chip at 390 and the phase head at 1280 are in runs mode; the Now card is in cell mode.
- The paused part has `background-size` `100% 50%`, `background-position` `0% 100%`, and no `::after` content.
- `--muted` and `--holds`, read from the computed `:root`, each reach 3:1 against `--surface`.
- Re-point: the test "a paused cell narrower than 3px paints apart from a done cell" asserts a cell under 3px and
  samples painted pixels. No cell under 3px is drawn after this change, so it is replaced by the checks above.

## Critique (impeccable, single context)

Degraded: single context, no sub-agent tool in a designer, and the context launcher is refused here. The detector found
nothing; it reads the harness, not the screen in the frames.
- Open: one screen can show one phase two ways. At 1280 the Now card and rail chip draw 30 cells while the phase head
  draws runs. The same question as the roadmap notes: is that acceptable, or should all of a phase's bars go to runs
  together (JS, one layout read per render)?
- Open: in dark the done block and the paused low cell share one colour (1.02:1). Height alone tells them apart; the
  in-progress and stalled blocks sit between them in the fixture, but a phase with neither puts them side by side.
- Open: at the 4px floor a 1-step run reads larger than its share. The d/n count is exact.
- Fixed: none needed in the bars. The harness labels sit below the bars, so they cover no cell.

## Seen, outside this lane

- In forced-colors mode the bar cells lose their backgrounds, stripes and low half, as every cell does today.
- The mockup leaves the side column empty at 1280; only the bars change.
