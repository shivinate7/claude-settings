# House UX rules live in docs/design/

## The ruling

The UX rules that every repo with screens shares, beyond the three third-party sets, live in `docs/design/`. They
come from the owner's own repos. Each rule cites its repo and entry. A rule that no repo shows is left out.

- The house rules are `ux-answer-at-press`, `ux-long-run-stops`, `ux-all-is-well` and `ux-thumb-zone`.
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
- "Say it once, in the fewest words" is left out, because impeccable `clarify` and the UI-string clause in
  `agents/reviewer.md` already hold it.
- Not house rules: behaviour defaults (dropped); spend shows cost, work-screen head, real photos only and
  phone-first (per repo); letter case (Vercel).

Reopen when a rule clashes with a repo's own ruling twice, or a third-party set starts to state a house
rule. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: docs/design/principles.md
