# Taken-picks area: design result and triage's picks

Step: page-taken-picks-area (goal v6, row 2). Designer (opus) report, 19:14 CST Nov 18. Mockup: taken-picks.html (deep links `#s=cards|pressed|overruled|routed|empty`, plus `&w=390|1280`, `&t=light|dark`). Notes: taken-picks-notes.md (9 items). Screenshots stay in the scratchpad (28 MB) and are not kept.

## What the design decides
- Marker: a new `taken` object on a closed decision item: `{by, at, what, changes, against?, ended?, over}`. Today only the `taken-` id prefix and title words mark one. Never `stands` or `pick` (the 15 Nov ruling, step page-no-preselected-pick). Sort key: `taken.at` (all five items share one `added`).
- Place: after the open tiers, before Answered. Taken items leave Answered. "Last 24 hours" and "Older" groups, newest first; Older open on load. Empty area: one sentence.
- Overrule: one toggle, never pressed on load, no Keep button. Undo is the existing three (second press, "Undo send" for 8 s, then Change). Send writes `choice: "overrule"`; the owner session reopens the item in its tier, as an overturn does today.
- Builder gap: skills/waiting-page/page_grant.py rule 4 refuses an answer on a closed item that is neither a ruling nor a routed close; it needs a taken branch.
- Writer backfill: `taken` and shorter titles on the five existing items.

## Triage's picks (undoable, taken under the owner's 20:18 CST Nov 14 words, shown in the area itself once built)
1. The `taken` field: yes. 2. Merged placement: after open tiers, before Answered: yes. 3. One act name, Overrule, also on Arbiter rulings: yes. 4. The `overrule` choice key and its route: yes.

## Open (designer's own flags)
The designer's critique ran single-context; the detector's empty result is unknown, not clean. Two guard refusals to judge as possible false alarms: other-checkout on a read-only grep of docs/design, and the worktree check on a scratchpad-only python write.
