# Roadmap Plan view: stalled and paused row tint, design notes

Mockup: `roadmap-stalled-row-tint.html`. The page CSS in it is an excerpt of
`skills/roadmap/page/index.html` at 12e3ea1a1 (the head of PR #1635, stalled and paused bar cells).
Sizes: Phone 390 and Wide 1280, the brief's sizes. This repo's device list reads "unknown". Themes:
light and dark, side by side by default. Sample data: one phase with an in-progress, a stalled, a
paused, a blocked, a to-do and a done step, and a Latest changes feed.

Deep links: `#st=tint|edge`, `&pz=grey|none`, `&wt=normal|bold`, `&w=all|390|1280`,
`&t=both|light|dark`, `&lab=off`, `&hide=tint,edge,grey,none,normal,bold`. Focus ids: `pick-stalled`
(stalled row), `pick-paused` (paused row), `pick-weight` (paused title).

Today: `stepRow` writes `class="st ${s.status}"`. A stalled or paused step keeps status `active`, so
`.st.active .rw` gives it the blue `--accent-soft` tint and the blue `--accent` edge.

## Items

1. **Stalled row, option Red tint and edge.** `--bad-soft` tint and a 3px `--bad` edge. The Stalled
   tag pill takes `--surface`, because its own `--bad-soft` fill is 1.00:1 against the tint.
   Gain: the row reads in the stalled band's red, as the mark, the tag and the bar cell do. It stays
   apart from a blocked row, which has a red edge and no tint.
   Loss: one more rule, for the tag pill.
   Pick: yes.

2. **Stalled row, option Red edge only.** No tint, a 3px `--bad` edge.
   Gain: the quietest form.
   Loss: a stalled row and a blocked row differ only by the mark, the tag and the bold title.
   Pick: no.

3. **Paused row, option Grey edge.** No tint, a 3px `--muted` edge.
   Gain: the row reads in the paused band's grey, as the mark, the tag and the ring cell do.
   `--surface-2` cannot be the tint: it is the `.rw:hover` colour and 1.05:1 against `--surface`.
   Loss: none seen.
   Pick: yes.

4. **Paused row, option No edge.** A plain row, as a to-do row.
   Gain: a parked step does not pull the eye.
   Loss: only the mark and the tag tell it from a to-do row.
   Pick: no.

5. **Paused title weight.** Option Normal weight sets 400. Option Bold, as today, keeps the 600 of
   `.st.active .ttl`. A stalled title stays bold in both.
   Gain: a stalled step asks for triage, so it stays bold. A paused step waits, so it is not bold.
   Loss: none seen.
   Pick: Bold, as today. A port keeps the existing behaviour by default (rule building-port-keeps-behaviour).

6. **Feed label.** No change. On 12e3ea1a1, `.kind.stalled{color:var(--bad)}` is there (the rule of
   the #1635 notes, item 1). `.kind.paused` has no rule, so it is `--muted` from `.kind`. That is the
   paused band's colour already: the pause mark, `.tag.pzd` and the band's Paused summary all use
   `--muted`. The #1635 notes, item 1, picked "Paused keeps the grey `.kind` default". The builder may
   add `.kind.paused{color:var(--muted)}` so a test can pin it. That changes no pixel.

## Builder changes, `skills/roadmap/page/index.html` (the picks)

- JS, `stepRow`: add `stl-row` when `shown==='stalled'` and `pzd-row` when `shown==='paused'`, after
  `st ${s.status}`. These are the class names the waiting page uses.
- CSS, after `.st.blocked .rw` (line 179):
  - `.st.stl-row .rw{background:var(--bad-soft);box-shadow:inset 3px 0 0 var(--bad)}`
  - `.st.stl-row .tag.stl{background:var(--surface)}`
  - `.st.pzd-row .rw{background:none;box-shadow:inset 3px 0 0 var(--muted)}`
  - `.st.pzd-row .rw:hover{background:var(--surface-2)}`
- Optional: `.kind.paused{color:var(--muted)}` (item 6).
- No new token.
- The row CSS and `stepRow` are outside the build blocks, so re-pin `TODAY_TEMPLATE_SHA256` in
  `skills/roadmap/test_build.py`.

## Contrast (measured, WCAG 2 ratio, light / dark)

| Pair | Light | Dark |
|---|---|---|
| Stalled row: title `--ink` on `--bad-soft` | 14.13 | 13.27 |
| Stalled row: edge `--bad` on `--bad-soft` | 5.36 | 6.86 |
| Stalled row: tag mark `--bad` on `--surface` pill | 6.46 | 7.62 |
| Stalled row: chevron `--muted` on `--bad-soft` | 4.22 | 5.72 |
| Paused row: title `--ink` on `--surface` | 17.04 | 14.75 |
| Paused row: edge `--muted` on `--surface` | 5.09 | 6.35 |
| Paused row: tag mark `--muted` on `--surface-2` | 4.83 | 6.01 |
| Feed: Stalled `--bad` on `--surface` | 6.46 | 7.62 |
| Feed: Paused `--muted` on `--surface` | 5.09 | 6.35 |

The chevron is `aria-hidden` and the `.meta` box holds only tags, so `--muted` on the row is
non-text: the limit is 3:1. Today's in-progress row has the same pair at 4.30 (light).

## Tests that touch these rows (`skills/roadmap/tests/page.test.mjs`)

- "a paused step's row reads Paused, never In progress".
- "a stalled step carries the Stalled tag and the Doing now mark at first load, with no live lane".
- "control: the Blocked label computes to the --bad colour in" each scheme, and "the Stalled label
  of a stalled step computes to the --bad colour in" each scheme.
- The Latest changes and Changes log tests that read Stalled or Paused in `.kind`.
- "a ... step listed ... carries no Stalled or Paused tag" and its control.
- No test pins a row's background or edge. A test-author adds three. A stalled row's background is
  `--bad-soft` and its edge `--bad`. A paused row has no `--accent-soft` background and a `--muted`
  edge. A live in-progress row keeps both accent values (control).

## Critique (impeccable, single context: no agent tool in a designer)

The detector found nothing. It reads the harness, not the screen in the frames.
- Fixed: the harness labels covered the Now and Blocked tags at 1280. They now sit on the row's top
  edge.
- Open: a forced-colors mode drops the tint and the inset edge. The mark and the tag carry the state.
  This is true of every row today.
- Open, outside this lane: at 390 the 34px id column wraps an id of five or more characters. This
  is true today.
