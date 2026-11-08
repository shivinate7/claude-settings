# Roadmap Plan view: stalled and paused, design notes

Mockup: `roadmap-stalled-paused.html`. Drawn from `skills/roadmap/page/index.html` at 38a463f8e (the
branch of PR #1522, stalled and paused steps stop reading "In progress"). The page CSS in the mockup is
the page's own two style blocks at that commit; the page's later `.grp` nowrap rule is not in it. Sizes: Phone 390 and Wide 1280, the brief's sizes.
This repo's device list reads "unknown". Themes: light and dark. Sample data: a phase of 12 steps and a
phase of 30 steps.

Deep links: `#s=mixed|dense`, `&o=hatch|tint`, `&c=on|off`, `&w=all|390|1280`, `&t=light|dark`,
`&lab=off`, `&hide=hatch,tint,on,off`. Focus ids: `pick-kind` (feed), `pick-bars` (phase head bar),
`pick-count` (Now card count line).

## Items

1. **Stalled in the feed is red.** `.kind.stalled` gets `--bad`, as `.kind.blocked` has. Paused keeps
   the grey `.kind` default.
   Gain: the feed agrees with the stalled band, its mark and the row tag, which are all red. The same
   rule fixes the Changes view, because `renderLog` uses `.kind` too.
   Loss: Stalled and Blocked share one colour in the feed. The word tells them apart.
   Pick: yes.

2. **Bar cells, option Hatch and ring.** A stalled cell is red stripes (`--bad` on the card). A paused
   cell is a grey ring (`--muted`). No new colour.
   Gain: each cell differs from its neighbour by shape: solid accent (done), faded accent (in
   progress), stripes (stalled), ring (paused), solid red (blocked), solid grey (to do). The roadmap
   bars are not aria-hidden, so the cell must not rely on colour alone. The ring echoes the pause
   mark's ring.
   Loss: in a rail chip at 390 a cell is 2.25 px wide at 13 steps and 0 px at 30. There the stripes and
   ring fade to a mid red and a mid grey. At 1280 and 30 steps a phase head cell is 1.06 px at 1x,
   so the shapes show only at 3x.
   Pick: yes.

3. **Bar cells, option Tint.** Stalled is `--bad` at 45 % and paused is `--muted` at 45 %, as `.act`
   tints the accent.
   Gain: two short rules, and the same idiom as in progress.
   Loss: colour alone. In dark, a paused cell is hard to tell from a to-do cell (measured, Wide 1280
   dark).
   Pick: no.

4. **Count words in the Now card.** The line reads "4 of 12 done · 1 in progress · 1 stalled · 1
   paused". Option No count words keeps today's line.
   Gain: the counts that the bar shows are also in words, so no reader needs the cells.
   Loss: "stalled" shows once more on the screen. It is in a sentence, so `ux-label-once` passes it.
   Pick: yes.

5. **Cell order.** Done, in progress, stalled, paused, blocked, to do.
   Gain: the steps that hold status active sit together, next to in progress.
   Loss: blocked moves one place right, after stalled and paused.
   Pick: yes.

6. **Bar names.** The Now card bar and the phase head bar get `role="img"`, an `aria-label` and a
   `title`, such as "4 done, 1 in progress, 1 stalled, 1 paused, 5 to do". Each rail button's
   `aria-label` adds ", 1 stalled, 1 paused" where the count is not 0.
   Gain: a screen reader and a hover read every cell kind.
   Loss: none seen.
   Pick: yes.

## Builder changes, `skills/roadmap/page/index.html`

- CSS: `.kind.stalled{color:var(--bad)}`.
- CSS: `.bar i.stl{background:repeating-linear-gradient(135deg,var(--bad) 0 2px,transparent 2px 4px)}`.
- CSS: `.bar i.pzd{background:transparent;box-shadow:inset 0 0 0 1.5px var(--muted)}`.
- JS: `segs(counts, n)` over `tally` emits `<i class="stl">` and `<i class="pzd">` in the order of item 5. Count
  `t` and `p` with `shownState(s)==='stalled'|'paused'`. Change all three calls: `renderNow`,
  `renderRail` and `renderPhase` (the `.ph-head .prog` bar).
- JS: the bar names and rail labels of item 6, and the Now card words of item 4.

## Blocked cells

- `renderNow`, `renderRail` and `renderPhase` each pass the blocked count to `segs`, so every bar draws
  a blocked step red. The mockup draws it as to do in the Now card and phase head bars.

## Critique (impeccable, single context: no agent tool in a designer)

The detector found nothing. It reads the harness, not the screen in the frames.
- Fixed: the harness labels on the Now card covered the phase name. They now sit at the card's
  foot. At 390 the label still covers part of "Whole plan"; Labels off clears it.
- Open: nothing on the screen teaches that stripes mean stalled and a ring means paused, except the
  bar's `title` on hover. The count words (item 4) carry it in the Now card. The phase head has no
  words. A question for the owner, not blocking: is the stalled band's red mark enough of a key?
- Open: paused cells under ~3px read like done (measured 1.08-1.25:1 on the roadmap tokens); lane `nfp-narrow-paused-cell`
  gives them a non-colour cue.
- Open: Tint (item 3) fails in dark. It stays only so the owner can cull it.

## Seen, outside this lane

- A stalled or paused row keeps `.st.active`: a blue tint and a blue edge, as an in-progress row. The
  waiting page gives a stalled row a red edge (`.rsteps .stl-row`).
- At 390, a rail chip with 30 or more steps draws no bar: the 2 px gaps take its whole width. This is
  true today, with no stalled step.
- In forced-colors mode the bar cells lose their backgrounds, stripes and ring. This is true of every
  cell today.
