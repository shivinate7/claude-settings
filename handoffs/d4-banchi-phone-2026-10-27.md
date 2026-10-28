# d4 hand-off: blind Banchi phone design, paused

Paused Oct 27 13:32 CDT on shiv's usage-limit pause.

- Done: the blind brief, `designs/d4-banchi-phone/banchi-phone-blind-1.md`. `hooks/blind_brief.py` passed it (0 faults).
- Not done: the designer was stopped before it wrote a file. No mockups, no pictures, no review.
- To resume: spawn one Opus designer with that brief and the delivery list from `briefs/d4-banchi-phone-blind-design.md` (3 to 5 directions, Duo folded first, states empty, loading, list, error, a PNG per state and one overview PNG per direction). Write to `designs/d4-banchi-phone/`. Then one Opus design reviewer.
- Assumption to confirm: no Duo size is written anywhere (`lint/layout.json` gives null). The brief draws folded at 360x780 and unfolded at 760x780.
- Corrected Oct 28 (triage 9): the Designs tab on main is c112's. d9 (a picture per option inline) is not on main: its commits are only on the c126 lane branch claude/project-thread-xczmrz. Main holds #713 (a mockup inside each option card), which overlaps d9.
