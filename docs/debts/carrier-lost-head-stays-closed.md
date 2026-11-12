# An open carrier that lost its head keeps its carried PR closed

- **What.** An open carrier that lost the head never reopens the PR it carried. So a lane dropped on a red run stays closed as carried. Red-run drops are common, and step 8 of `ci-hygiene` (Batch lanes) gives the runner a fix lane for each drop, so this happens in normal work. Accepted for now: a fix would add reads on each wake.
- **Where.** `merge/merge.py`, `reopen_lines`. It reopens a carried PR only when the carrier closes unmerged, and a lane drop leaves the carrier open. The same rule is in `skills/ci-hygiene/SKILL.md`, step 8: "A Carried note reopens only when R closes unmerged."
- **Decision.** `session-tiers` (session roles), replaced-drafts bullet. Its scope add, owner ruling 2026-11-09 21:29 CST, says a carried PR "reopens if the carrier is dropped". The bullet's reopen rule fires only when the carrier closes unmerged, so a lane drop does not reach it.
- **Retire.** A new case in `merge/test_close_replaced.py`, red before the fix and green after: an open carrier that no longer holds the carried PR's head reopens that PR.
