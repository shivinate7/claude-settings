# A relayed hand-off re-runs the lint in each new container

- **What.** The send-time check of rule `lane-lint-send` also requires the lane-lint marker of the live head in the sender's own container. The marker is per container. A coordinator relay, a resumed lane or a rotated runner must run `merge --lane-lint` (about 11 min) before sending a pull request whose review record already proves a pass. The marker guards only against a hand-typed record. Lane pick, kept, 2026-11-08 CST.
- **Where.** `hooks/guard_merge.py` `lane_lint_send_hit` (~1786-1794, the no-marker refusal); `merge/merge.py` `hand_off_read` (~3378, `lane_lint_passed`).
- **Decision.** `lane-lint-send` (a lane hands a batch runner only a pull request whose live head passed its lint).
- **Retire.** The review record carries its own lint proof. A case in family `lane-lint-send` in `hooks/test_guard.py` shows a record with that proof passing in a container with no marker.
