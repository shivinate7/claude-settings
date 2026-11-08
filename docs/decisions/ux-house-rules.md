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

- The house rules (owner, item 183 (ux-house-rule-ids, which UX rules are house rules): note
  2026-11-06 11:22 CST, picks 13:11 CST). Each id has its entry in `principles.md` (P) or
  `layout.md` (L) in `docs/design/`:
  - `ux-answer-at-press` (P): the answer to a press shows at the control.
  - `ux-long-run-stops` (P): a run of more than a few seconds has a Stop control.
  - `ux-all-is-well` (P): a status summary names only what is not normal.
  - `ux-thumb-zone` (P): on a phone, the main input and action are in thumb reach.
  - `ux-label-once` (P): a label or status word shows once on a screen.
  - `ux-works-when-script-fails` (P): content and the main action work with script or WebGL off.
  - `ux-lost-scene-recovers` (P): a 3D scene shows words on context loss and comes back.
  - `ux-still-scene-draws-nothing` (P): a 3D scene at rest draws nothing.
  - `ux-canvas-has-words` (P): a canvas that informs has a name, text and keyboard acts.
  - `ux-scroll-stays-native` (P): the page scrolls by its usual steps.
  - `ux-forced-colors-hold` (P): controls, edges, focus and state show in forced colours.
  - `ux-full-height-fits` (P): each `vh` value has an `svh` or `dvh` fallback after it.
  - `ux-vitals-measured` (P): LCP, INP and CLS are measured "good".
  - `ux-feature-baseline-or-fallback` (P): a new browser feature sits behind a test, with a fallback.
  - `ux-unknown-is-not-empty` (P): loading, failed, unknown, empty and loaded differ; an empty state
    is one sentence and one control.
  - `ux-haptics-feel-substantial` (P): a control that changes a value considers a haptic.
  - `ux-keep-what-was-made` (P): input no server can return survives leaving and coming back.
  - `ux-control-earns-place` (P): a control that changes nothing is absent; an off one says why.
  - `ux-one-plain-name` (P): one name per screen and act, one meaning per icon.
  - `ux-gap-on-parent` (L): the parent spaces its children with `gap`.
  - `ux-layout-primitives` (L): a page is built from named layout primitives.
  - `ux-component-reads-its-box` (L): a shared component picks its shape from its own width.
  - `ux-variant-extends-home` (L): a variant extends its shared component, never copies it.
  - `ux-fluid-tokens` (L): sizes that grow with the box come from tokens.
- Guidance, not house rules: `ux-order-holds-still`, `ux-statements-are-true`, `ux-no-dead-end`,
  `ux-machine-text-hidden`, `ux-a11y-floor`, `ux-text-zooms` (P) and `ux-control-beside-area` (L). Each entry says
  "Guidance", and a miss is advice, not a finding.
- Not adopted: `ux-press-moves-nothing` (P), item 183 option b (owner, 2026-11-06 13:11 CST). A lane checks
  `ux-swift-same-intent` (L), roadmap step ux-swift-same-intent-check.
- `ux-empty-one-action` is part of `ux-unknown-is-not-empty`. `ux-ask-or-undo` is not a rule.
- Touch size is the Target size row in `docs/design/a11y.md`: 44px on touch, 24px for mouse.
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
- `ux-order-holds-still` lets an act move the row it acted on out of an open list. The next open
  row then takes its slot, and the other rows keep their order (owner, 2026-11-06 16:47 CST, item
  313 a). The owner on item 311 (15:51 CST): the rule was "applied too strictly and is taking me away from the
  outcome I want".
- `ux-order-holds-still` also lets the rows that close its gap and the rows that make room where
  it lands shift, in their order (item 313 a). A count badge or section header that the sink
  shifts may shift too (owner, 2026-11-06 17:19 CST, item 318 a).
- Not rules: behaviour defaults (dropped); spend shows cost, work-screen head, real photos only and
  phone-first (per repo); letter case (Vercel).

Reopen when a rule clashes with a repo's own ruling twice, or a third-party set starts to state a house
rule. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: docs/design/principles.md
