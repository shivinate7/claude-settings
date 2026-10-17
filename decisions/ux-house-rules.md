# House UX rules live in ux/

## The ruling

The UX rules that every repo with screens shares, beyond the three third-party sets, live in `ux/`. The
rules come from the owner's own repos (banchi, q_max, joyous, degen, sillage, home-app, ios-adblock). Each
rule cites its repo and entry. A rule that no repo shows is left out.

- The house rules are `ux-answer-at-press`, `ux-long-run-stops`, `ux-all-is-well` and `ux-thumb-zone`.
  Touch size is the Target size row in `ux/a11y.md`: 44px on touch, 24px for mouse.
- House design values are in `ux/tokens.md`, and a repo may override them: spacing and radius, color by
  role (light and dark), system font, and phone bottom nav. Motion durations and easing are per repo.
- One id per rule (`ux-<slug>`): the checklist, a finding and a clash all cite the same id.
  `ux/principles.md` holds one entry per rule: its id, one rule sentence, one pass/fail check, and its
  source. `ux/checklist.md` holds one yes or no line per id, marked once per changed screen.
- The folder is `ux/`, not `CLAUDE.md`, because `CLAUDE.md` loads in each session, also in repos with no
  screen. Skill design-review, `agents/builder.md` and `agents/reviewer.md` read `ux/` only where screens
  exist.
- `ux` is in `landed-dirs.txt` (landed at `~/.claude/ux/`) and in `CONFIG_FROZEN_DIRS` in `hooks/guard.py`.
- A house rule states only the house difference. Example: impeccable prefers undo when recovery is safe,
  and `ux-ask-or-undo` adds "never both, never neither", the count, and first focus on Cancel.
- The third-party sets keep their parts (`design-skills`):
  - Vercel web-interface-guidelines: web mechanics (labels, focus, forms, touch, copy case).
  - impeccable: critique and polish. This covers a plain error with Try Again, a next step for an empty
    state, undo before a confirm, and one noun for one concept.
  - frontend-design: visual direction.
- "Say it once, in the fewest words" is left out, because impeccable `clarify` and the UI-string clause in
  `agents/reviewer.md` already hold it.
- Ruled per repo or dropped, not house rules: behaviour defaults (dropped); spend shows cost (per repo);
  letter case (Vercel); work-screen head (per repo); real photos only (per repo); phone-first (per repo).
  Repo-specific flavor stays with each repo.

Reopen when a rule clashes with a repo's own ruling twice, or a third-party set starts to state a house
rule. Then follow `outcomes-stale-decision-protocol`.

Kind: process
Home: ux/principles.md
