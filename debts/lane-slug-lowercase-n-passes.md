# Lowercase lane numbers and four-digit numbers pass

- **What.** Lowercase `n20` passes. Four-digit numbers pass.
- **Where.** `LANE_NUMBER` in `hooks/guard.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** A case with `n20` is refused, and the digit limit is either widened or recorded as a limit.
