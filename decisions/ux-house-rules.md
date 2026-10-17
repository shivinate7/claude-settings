# House UX rules live in ux/

## The ruling

The UX rules that every repo with screens shares, beyond the three third-party sets, live in `ux/`. The
rules come from the owner's own repos (banchi, q_max, joyous, degen, sillage, home-app, ios-adblock). Each
rule cites its repo and entry. A rule that no repo shows is left out.

- Four candidates became rules: `ux-answer-at-press`, `ux-long-run-stops`, `ux-all-is-well` and
  `ux-thumb-zone`. Touch size is the Target size row in `ux/a11y.md`: 44px on touch, 24px for mouse.
- House design values are in `ux/tokens.md`, and a repo may override them: spacing and radius, color by
  role (light and dark), system font, and phone bottom nav. Motion durations and easing are per repo, not
  a default.

Layout:

- `ux/principles.md`: one entry per rule, with an id (`ux-<slug>`), one rule sentence, one check that a
  reviewer marks pass or fail, and its source.
- `ux/checklist.md`: one yes or no line per rule id, marked once per changed screen.
- `ux/a11y.md`: the accessibility floor (WCAG 2.2 AA) and the CI check, with axe for web and the XCUITest audit for iOS.
- `ux/README.md`: what the folder is, and who loads it.
- `ux/tokens.md`: the house design values.
- A folder, not `CLAUDE.md`: `CLAUDE.md` loads in each session, also in repos with no screen. Skill
  design-review, `agents/builder.md` and `agents/reviewer.md` name the files they read in this folder, and
  read them only where screens exist.
- One id per rule: the checklist, a finding and a clash all cite the same id.

What stays with the third-party sets (the design-skills record holds them):

- Vercel web-interface-guidelines: web mechanics, such as labels, focus, forms, touch and copy case.
- impeccable: critique and polish. Its `clarify` and `harden` references cover a plain error and Try
  Again, a next step for an empty state, undo before a confirm, and one noun for one concept.
- frontend-design: visual direction.

A house rule states only the house difference. Example: impeccable prefers undo when recovery is safe, and
the house rule `ux-ask-or-undo` adds "never both, never neither", the count, and first focus on Cancel.
"Say it once, in the fewest words" (q_max D-709) is left out, because impeccable `clarify` and the
UI-string clause in `agents/reviewer.md` already hold it.

Ruled per repo or dropped, not house rules:

- Behaviour defaults: dropped (archiving starts off, sold items fold away, a default year does not move with the calendar, the theme follows the system).
- Spend shows cost: per repo (banchi D33 and D224).
- Letter case: left to Vercel (q_max D-666).
- Work-screen head: per repo (`specs/ux-plan-b.md`, choice 3).
- Real photos only: per repo (joyous `docs/design-brief.md` move 7).
- Phone-first: per repo.

Repo-specific flavor stays with each repo, for example banchi's refusal toasts, which stay until dismissed.

`ux` is in `landed-dirs.txt`, so the installers land it at `~/.claude/ux/`. It is also in
`CONFIG_FROZEN_DIRS` in `hooks/guard.py`, as `hooks/`, `lint/` and `agents/` are. The builder,
design-review and reviewer wiring name that path. `lint/check_landed_dirs.py` keeps the two lists in
agreement.

Reopen when a rule clashes with a repo's own ruling twice, or a third-party set starts to state a house
rule. Then follow outcomes-stale-decision-protocol.

Kind: process
Home: ux/principles.md
