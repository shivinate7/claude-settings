# Waiting page Status tab: stalled and paused row tint, design notes

Mockup: `status-stalled-row-tint.html`. The page CSS in it is an excerpt of
`skills/waiting-page/page.html` at 12e3ea1a1 (the head of PR #1635), with the default brand. The
phase box is drawn alone, not in the tab's full layout. Sizes: Phone 390 and Wide 1280, the brief's
sizes. This repo's device list reads "unknown". Themes: light and dark, side by side by default.
Sample data: one phase with an in-progress, a stalled, a paused, a blocked and two to-do steps.

Deep links: `#st=tint|edge`, `&pz=grey|none`, `&wt=normal|bold`, `&w=all|390|1280`,
`&t=both|light|dark`, `&lab=off`, `&hide=tint,edge,grey,none,normal,bold`. Focus ids: `pick-stalled`
(stalled row), `pick-paused` (paused row), `pick-weight` (paused title).

Today: `stepRow` writes `class="${s.status}"` and adds `stl-row` for a stalled step. A stalled row
keeps the `--acc-soft` tint of `.rsteps .active > .rrow` under its red edge. A paused row gets no
class of its own, so it keeps the tint and the `--acc` edge of an in-progress row.

## Items

1. **Stalled row, option Red tint and edge.** `color-mix(in srgb, var(--holds) 14%, var(--surface))`
   and the 3px `--holds` edge the page already draws. The mix is the page's own red tint, from
   `.dl.bad`. The page has no `--holds-soft`, and this adds none.
   Gain: the row reads in the stalled band's red. It stays apart from a blocked row (red edge, no
   tint). The mix follows a brand's `--holds`.
   Loss: none seen.
   Pick: yes.

2. **Stalled row, option Red edge only.** No tint.
   Loss: a stalled row and a blocked row differ only by the mark, the tag and the bold title.
   Pick: no.

3. **Paused row, option Grey edge.** No tint, a 3px `--muted` edge.
   Gain: the row reads in the paused band's grey.
   Loss: with the default brand, `--muted` and `--acc` are close (1.09:1 light, 1.02:1 dark). So a
   paused row differs from an in-progress row by the tint, the mark and the tag,
   not by the edge colour. `--chip` cannot be the paused tint: it is 1.02:1 against `--acc-soft` in
   light and the same hex in dark.
   Pick: yes.

4. **Paused row, option No edge.** A plain row, as a to-do row.
   Loss: only the mark and the tag tell it from a to-do row.
   Pick: no.

5. **Paused title weight.** Option Normal weight sets 400. Option Bold, as today, keeps the 700 of
   `.rsteps .active .ttl`. A stalled title stays bold in both.
   Pick: Bold, as today, as on the roadmap. A port keeps the existing behaviour by default (rule
   building-port-keeps-behaviour).

## Builder changes, `skills/waiting-page/page.html` (the picks)

- JS, `stepRow`: add `pzd-row` when `pzd`, beside the `stl-row` it adds now.
- CSS, change line 609 and add after it:
  - `.rsteps .stl-row > .rrow { background: color-mix(in srgb, var(--holds) 14%, var(--surface)); box-shadow: inset 3px 0 0 var(--holds); }`
  - `.rsteps .pzd-row > .rrow { background: none; box-shadow: inset 3px 0 0 var(--muted); }`
  - `.rsteps .pzd-row > .rrow:hover { background: color-mix(in srgb, var(--chip) 60%, transparent); }`
- No new token. The tags need no change: `.tag` has no fill, only a `currentColor` border.

## Contrast (measured, WCAG 2 ratio, default brand, light / dark)

| Pair | Light | Dark |
|---|---|---|
| Stalled row tint (`--holds` 14%) | #f4e1df | #392d32 |
| Stalled row: title `--ink` on the tint | 13.74 | 11.09 |
| Stalled row: id `--muted` on the tint | 5.14 | 5.79 |
| Stalled row: tag and edge `--holds` on the tint | 5.19 | 5.80 |
| Paused row: title `--ink` on `--surface` | 17.30 | 14.10 |
| Paused row: id, tag and edge `--muted` on `--surface` | 6.47 | 7.37 |

A brand that sets `--r-*` changes `--holds`, `--acc` and `--acc-soft`. These numbers hold for the
default brand only.

## Tests that touch these rows (`skills/waiting-page/tests/page.test.mjs`)

- "the row labels of a to-do step listed paused and a done step listed stalled read To do and Done".
  It also checks that those rows carry no Stalled or Paused tag.
- No test pins the `stl-row` edge or any row background. A test-author adds three. A stalled row's
  background is the `--holds` mix and its edge `--holds`. A paused row has no `--acc-soft`
  background and a `--muted` edge. A live in-progress row keeps both accent values (control).
- No test pins this page's hash.

## Critique (impeccable, single context: no agent tool in a designer)

The detector found nothing. It reads the harness, not the screen in the frames.
- Fixed: the harness labels covered the tags at 1280. They now sit on the row's top edge.
- Open: a forced-colors mode drops the tint and the inset edge. The mark and the tag carry the state.
  This is true of every row today.
