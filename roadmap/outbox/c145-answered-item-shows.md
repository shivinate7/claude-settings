# c145-answered-item-shows

Status: done, green and reviewed. Draft PR #744 (c145, answered item shows), head dcd78a1b.

- Red first: 33597cfb, the new tests red on the old page (no `.ans` badge). Green: 677fbf4c and dcd78a1b.
- Gates: page tests PASS, `ci-job gates --lint` PASS, `check_silent_undo --strict` ALLOWED (Drops-lines trailers for the two re-pointed tests).
- Design: designer opus, design reviewer opus (round 1: 390 FAIL on a split time; fixed), design reviewer sonnet (round 2: 390 and 1280, light and dark, all PASS).
- Code: builder sonnet, reviewer sonnet in 2 rounds. Round 1 blocking (a stale receipt showed "filed" on a changed answer) is fixed with `rcOf`.

Notes (not debts):
- `rcOf` fails open when `answers.at` cannot be parsed. The page always writes `at`, so this is unlikely.
- At 390 wide, a long `home` makes the filed pill 4 lines tall. The time stays whole.
- An answered card keeps its locked open-card height, so it shows empty tint (pre-existing on main).
- On an answered card the green edge replaces the Blocking/Upcoming edge, and "about N min" is hidden (designer's call).
