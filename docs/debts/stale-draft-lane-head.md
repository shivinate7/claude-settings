# Stale-draft check misses a lane/<id> branch

- **What.** `stale_drafts` takes a draft as lane-owned only when its bare branch equals a live session step. A draft on `lane/<id>` with a live cs-step session for `<id>` therefore reads stale, and the upkeep row flags a live lane. The comment at that line says `lane/<id>` counts; the code checks only the bare branch.
- **Where.** `skills/roadmap/build.py` `stale_drafts`, the `sessionSteps` test (line 1030).
- **Decision.** `stalled-steps` (live lane: a session tagged cs-step, or an open PR on `<id>` or `lane/<id>`).
- **Retire.** `stale_drafts` reads a session step's lane as live for both `<id>` and `lane/<id>`, through `lane_head_refs` as `lane_live` does. A test in `skills/roadmap/test_build.py` shows a draft on `lane/<id>` with a live cs-step session is not stale.
