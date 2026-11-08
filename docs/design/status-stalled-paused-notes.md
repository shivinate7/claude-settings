# Waiting page Status tab: stalled and paused, design notes

Mockup: `status-stalled-paused.html`. Drawn from `skills/waiting-page/page.html` at 38a463f8e (the
branch of PR #1522, stalled and paused steps stop reading "In progress"). The page CSS in the mockup is
the page's own style block at that commit; the page's later `.grp` nowrap rule is not in it. Sizes: Phone 390 and Wide 1280, the brief's sizes. This
repo's device list reads "unknown". Themes: light and dark. Sample data: a phase of 12 steps and a
phase of 30 steps.

Deep links: `#s=mixed|dense`, `&o=hatch|tint`, `&c=on|off`, `&w=all|390|1280`, `&t=light|dark`,
`&lab=off`, `&hide=hatch,tint,on,off`. Focus ids: `pick-bars` (phase head bar), `pick-count` (Now
card count line).

The Latest changes feed needs no change here: each row carries the coloured mark (`rgl`), and the
stalled mark is already red.

## Items

1. **Bar cells, option Hatch and ring.** A stalled cell is red stripes (`--holds` on the card). A
   paused cell is a grey ring (`--muted`). The page has no `--holds-soft`, so the stripes alternate
   with `transparent`. No new colour.
   Gain: the cells read as the roadmap's, one family. Stalled differs from solid red blocked, and
   paused from solid grey to do, by shape.
   Loss: every `.segbar` here is `aria-hidden`, so the colour-alone rule does not require the shape.
   In a rail chip at 390 (104.7 px, measured at 24b1f98e3) a cell is 6.2 px wide at 13 steps and 1.55 px at 30; the ring fills the cell at 30.
   Pick: yes, so both pages draw one bar.

2. **Bar cells, option Tint.** Stalled is `color-mix(in srgb, var(--holds) 45%, transparent)`, paused
   the same with `--muted`, as `.act` mixes the accent.
   Gain: two short rules, the page's own idiom.
   Loss: colour alone. Paused is hard to tell from to do in dark.
   Pick: no.

3. **Count words in the Now card.** The line reads "4 of 12 done, 1 in progress, 1 stalled, 1 paused".
   Option No count words keeps today's line.
   Gain: the Now bar is aria-hidden, so this line is its only text. Today a stalled step drops out
   of it.
   Loss: "stalled" shows once more on the screen. It is in a sentence, so `ux-label-once` passes it.
   Pick: yes.

4. **Cell order.** Done, in progress, stalled, paused, blocked, to do. The same as the roadmap.
   Pick: yes.

5. **Spoken counts.** Each rail button's `aria-label` and the phase head's `.sr` text add ", 1
   stalled, 1 paused" where the count is not 0.
   Gain: a screen reader hears what the hidden bar shows.
   Pick: yes.

## Builder changes, `skills/waiting-page/page.html`

- CSS: `.segbar i.stl { background: repeating-linear-gradient(135deg, var(--holds) 0 2px, transparent 2px 4px); }`.
- CSS: `.segbar i.pzd { background: transparent; box-shadow: inset 0 0 0 1.5px var(--muted); }`.
- JS: `segs(counts, n)` over `tally` emits `<i class="stl">` and `<i class="pzd">` in the order of item 4.
  Count `t` and `p` with `shownState(s)`. Change all three calls: `renderNow`, `renderRail` and the
  phase head in the phase view.
- JS: the Now card words of item 3, and the labels of item 5.

## Blocked cells

- `renderNow`, `renderRail` and the phase head each pass the blocked count to `segs`, so every bar draws
  a blocked step red. The mockup draws it as to do in the Now card bar.

## Critique (impeccable, single context: no agent tool in a designer)

The detector found nothing. It reads the harness, not the screen in the frames.
- Fixed: the harness labels on the Now card covered the phase name. They now sit at the card's foot.
- Open: paused cells under ~3px read like done (measured 1.02-1.09:1 on this page's tokens); lane `nfp-narrow-paused-cell`
  gives them a non-colour cue.
- Open: Tint (item 2) fails in dark. It stays only so the owner can cull it.

## Seen, outside this lane

- A stalled row keeps the `.active` blue tint under its red edge. A paused row keeps the tint and the
  blue edge.
- In forced-colors mode the bar cells lose their backgrounds, stripes and ring. This is true of every
  cell today.
