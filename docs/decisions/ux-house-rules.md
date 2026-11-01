# House UX rules live in docs/design/

## The ruling

The UX rules that every repo with screens shares, beyond the three third-party sets, live in `docs/design/`. Most come from the owner's own repos, and each such rule cites its repo and record. A browser or 3D rule
that no repo shows may cite a standard or platform source instead (W3C, WHATWG, MDN, web.dev, GOV.UK,
a browser's, engine's or library's own docs, or a usability study). It sits under "Browser and 3D" in
`principles.md` (owner, 2026-11-01 12:21 CST, roadmap step web-design-guidelines: browser design dos
and don'ts, from static web apps to full 3D sites). Any other rule that no repo shows is left out.
A guideline becomes a house rule only when it makes the build better for the person who uses it, and
its rule sentence names that outcome. A standard level that is not legally required, such as a higher
WCAG level, is not taken on by choice (owner, 2026-11-01 12:23 CST, by triage).

- The house rules are `ux-answer-at-press`, `ux-long-run-stops`, `ux-all-is-well`, `ux-thumb-zone`,
  `ux-label-once`, `ux-works-when-script-fails`, `ux-lost-scene-recovers`, `ux-still-scene-draws-nothing`,
  `ux-canvas-has-words`, `ux-scroll-stays-native`, `ux-forced-colors-hold`,
  `ux-full-height-fits`, `ux-vitals-measured` and `ux-feature-baseline-or-fallback`.
  Touch size is the Target size row in `docs/design/a11y.md`: 44px on touch, 24px for mouse.
- House design values are in `docs/design/tokens.md`, and a repo may override them. Motion durations and easing are
  per repo.
- One id per rule (`ux-<slug>`): the checklist, a finding and a clash all cite the same id.
  `docs/design/principles.md` holds one entry per rule: its id, one rule sentence, one pass/fail check, and its
  source. `docs/design/checklist.md` holds one yes or no line per id, marked once per changed screen.
- The folder is `docs/design/`, not `CLAUDE.md`, because `CLAUDE.md` loads in each session, also in repos with no
  screen. Skill design-review, `agents/builder.md` and `agents/reviewer.md` read `docs/design/` only where screens
  exist.
- `docs/design` is in `landed-dirs.txt` and in `CONFIG_FROZEN_DIRS` in `hooks/guard_frozen.py`.
- A house rule states only the house difference.
- The third-party sets keep their parts (`design-skills`):
  - Vercel web-interface-guidelines: web mechanics (labels, focus, forms, touch, copy case).
  - impeccable: critique and polish (error text, empty-state next step, undo before a confirm, one noun
    for one concept).
  - frontend-design: visual direction.
- `ux-label-once` holds "say a label once" (owner, Oct 26 20:40 CDT: the waiting page repeated "Blocking",
  "Upcoming" and "Whenever"). impeccable `clarify` held it as advice, and nothing caught it.
  `lint/label_once.py` names each repeat in a rendered page. The probe skips controls and table cells. The
  reviewer judges each other hit.
- Not house rules: behaviour defaults (dropped); spend shows cost, work-screen head, real photos only and
  phone-first (per repo); letter case (Vercel).

Reopen when a rule clashes with a repo's own ruling twice, or a third-party set starts to state a house
rule. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: docs/design/principles.md
