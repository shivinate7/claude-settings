# A part code such as N12 is refused as a lane number

- **What.** Any `N` plus one to three digits, as a whole word, is refused. A part code such as `N12` is refused too. This is a false positive.
- **Where.** `LANE_NUMBER` in `hooks/guard.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** A case with a part code such as `N12` passes, and the pattern separates part codes from lane numbers.
