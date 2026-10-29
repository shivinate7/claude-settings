# c204-card-picture-scroll

Status: green and reviewed. Draft PR #806, head a057d856. Gates: ste-changed, silent-undo --strict and ci-job checks --lint pass on the head. The page suite passed 224/224 at 1c187d8a, and the head adds only debt notes.
- Built: a picture taller than its 480px box scrolls inside it, with a "More" cue. A focus box larger than the card scrolls inside the focus box and opens at its top (1A). A drag scrolls; a tap opens View; a scrollbar press opens and picks nothing. The 120px floor stays (5A). An overflow of 1px or less counts as fitting.
- Coordinator's added fix: `ol.steps` wraps an unbroken URL, so a task card no longer runs past a phone screen.
- Review: round 1 (haiku) failed on a scrollbar drag that opened View. Round 2 (sonnet) failed on a right press whose leftover state swallowed the next keyboard click. Round 3 (sonnet) passed. Design review (opus) passed at 12 width-theme pairs. axe was unknown: it is not installed here.
- Two notes in docs/debts/notes.md: waiting-page-gutter-cancel-keyboard-untested and waiting-page-gutter-cancel-script-click.
Deferred: two departures, not blocking, your call. 5B: a scrolling picture draws 221.8px wide (a phone picture's width), not 120px. The designer recommends it. It departs from fitFrame's scale and MIN_PIC. 1B: a focused card scrolls over the whole mockup, not only the focus box. It departs from SKILL.md "shows that element whole".
