# d4 redraw lane (blind pass v2, Banchi phone app)

- d4: done. The design reviewer passed the set in round 2 of 3 (9a899897). Three concepts in designs/d4-banchi-phone-v2/phone-blind-1.html: C1 Stack run (task first, tab bar), C2 Shelf (place first, boxes as bars of slots), C3 Only what needs you (bold: no list, no tab bar, the pose picks the mode). Option pictures png/c1-option.png, c2-option.png, c3-option.png pass c147. Agents: brief reviewer sonnet, designer opus, design reviewer opus (round 1) and sonnet (round 2).
- d4: deviation. The brief carries one blind lane with three concepts, per the coordinator's task, not design-explore's default mix of five lanes.
- d4: lint/layout.json has no written Duo size (size null), so the measured sizes from mailaudit measurement duo-fold-and-keyboard (2026-10-27) ride in the brief. Filing ask: write them into layout.json.
- d4: gap. The unfolded Duo height and all unfolded insets, and the folded top inset, are not measured. The designer drew 644 pt high unfolded and no folded status bar. Filing ask: the next Mac measurement adds them; whether the inner screen reports regular width is also unknown.
- d4: for triage. C3 has no tab bar, which departs from tokens.md "On a phone, navigation uses a bottom tab bar" (notes item 5, "Departs from:"). Ask it with the parked picks.
- d4: non-blocking. In C2 error folded light, a dashed "New:" tag covers "250 of 250" in the default view (l=0 hides it). Unfolded empty states leave the right pane blank.
