# The arbiter's merge tag is unconfirmed

**What.** Owner pick c (waiting-page item 867, 2026-11-15 11:37 CST) lets the arbiter merge under the standing merge role. The guard reads a session's tags only for the names in `STANDING_HOLDERS`, and no production code names the arbiter's tag. Only a guard test fixture uses `cs-build:arbiter`. So the arbiter cannot join `STANDING_HOLDERS` until its tag is confirmed in a live session. Until then its merge is refused, which is the safe side, and the pick does not take effect.

**Where.** `hooks/guard_merge.py`, `STANDING_HOLDERS` and `role_proof_hit`. The fixture is `ARBITER_TAGS` in `tests/guard/s13406-merge.py`.

**Decision.** `session-tiers` (session roles), its standing merge role sub-bullets, the follow-up bullet.

**Retire.** Confirm the arbiter's tag in a live session's `get_session` record. Then add it to `STANDING_HOLDERS`, and rewrite the follow-up bullet in place. The case that closes it is in `hooks/test_guard.py`: a record with the confirmed arbiter tag passes the standing tier, and a record without it is refused. The consultant's tag `cs-build:consultant` is already known, so it joins `STANDING_HOLDERS` in its own change and not through this debt.
