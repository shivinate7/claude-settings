# House UX rules live in ux/

## The question

Which UX rules does every repo with screens share, beyond the three third-party sets, and where
do they live?

## The ruling

Owner ruling, 2026-10-11: "build a ux folder". The rules come from the owner's own repos (banchi,
q_max, joyous, degen, sillage, home-app, ios-adblock). Each rule cites its repo and entry. A rule
that no repo shows is left out.

## Layout, and why

- `ux/principles.md`: one entry per rule, with an id (`ux-<slug>`), one rule sentence, one check
  that a reviewer marks pass or fail, and its source.
- `ux/checklist.md`: one yes or no line per rule id, marked once per changed screen.
- `ux/a11y.md`: the accessibility floor (WCAG 2.2 AA) and the CI check, with axe for web and the
  XCUITest audit for iOS.
- `ux/README.md`: what the folder is, and who loads it.
- Why a folder and not `CLAUDE.md`: `CLAUDE.md` loads in each session, also in repos with no
  screen. Skill design-review, `agents/builder.md` and `agents/reviewer.md` load the folder only
  where screens exist.
- Why one id per rule: the checklist, a finding and a clash all cite the same id.

## What stays with the third-party sets

The design-skills record (three design skills on screens) holds the three sets.

- Vercel web-interface-guidelines: web mechanics, such as labels, focus, forms, touch and copy
  case.
- impeccable: critique and polish. Its `clarify` and `harden` references cover a plain error and
  Try Again. They also cover a next step for an empty state, undo before a confirm, and one noun
  for one concept.
- frontend-design: visual direction.

A house rule states only the house difference. Example: impeccable prefers undo when recovery is
safe. The house rule `ux-ask-or-undo` adds "never both, never neither", the count, and first
focus on Cancel. "Say it once, in the fewest words" (q_max D-709) is left out. impeccable
`clarify` and the UI-string clause in `agents/reviewer.md` already hold it.

## Candidates, owner to decide

The evidence for each is thin or in conflict, so none is a rule yet.

- Defaults. Three principles, not one: archiving starts off (degen D3), sold items fold away
  (banchi D132), and a default year does not move with the calendar (q_max D-733). The theme
  follows the system (degen D29).
- The answer to a press shows where the press was (banchi D118 and UX-058, q_max D-640).
  But banchi puts a refusal in a toast, which stays until it is dismissed.
- A press that spends money shows the count and the cost first (banchi D33 and D224).
- A long run can be stopped (q_max D-319).
- A status summary names only what is not normal, else "All is well." (home-app `SPEC.md`).
- A name is Title Case and a sentence is sentence case (q_max D-666). Vercel asks Title Case
  for each heading and button.
- A work screen's head holds its name, its counts and its main action. banchi puts them on one
  line, and q_max uses a band with figure tiles (`specs/ux-plan-b.md`, choice 3).
- Primary inputs sit in the thumb zone (sillage `docs/design/system.md`).
- A house touch size above the WCAG 24 px: banchi uses 40 px, and sillage uses 44 px.
- Real photos only, with no stock or AI images (joyous `docs/design-brief.md` move 7).
- Phone-first stays per repo. joyous builds phone first. banchi (DEBT77) and q_max D-701 freeze
  phone work.

## Landing

`ux` is in `landed-dirs.txt`, so the installers land it at `~/.claude/ux/`. It is also in
`CONFIG_FROZEN_DIRS` in `hooks/guard.py`, as `hooks/`, `lint/` and `agents/` are. The builder,
design-review and reviewer wiring name that path. `lint/check_landed_dirs.py` keeps the two lists
in agreement.

## Reopen

Reopen when a rule clashes with a repo's own ruling twice, or a third-party set starts to state
a house rule. Then follow outcomes-stale-decision-protocol: name the sentence, measure the claim,
name the outcome, propose a fix, and wait for the owner.
