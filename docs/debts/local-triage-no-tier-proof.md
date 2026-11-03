# A local triage session cannot prove its tier

- **What.** Guard rule `roadmap-one-writer` refuses every push to a repo's record branch from a local Claude Desktop session, the triage session included. The proof reads only a cloud session: `override.remote_session_id()` is None unless the cloud env names a `cse_` id, and `_own_session_read` looks for a `get_session` result with a `ccr` field and a `cs-build:triage` tag. A local session's `get_session` returns `sessionId` (`local_...`), `title` and `parentSessionId`, with no tags, and no local tool sets tags. The refusal tells the session to run `get_session` and retry, which can never pass.
- **Where.** `hooks/guard_merge.py`: `record_writer_hit`, `_own_tier_proved`, `_own_session_read`, `RECORD_REASON`; `hooks/override.py` `remote_session_id`.
- **Decision.** `session-tiers` (bullet "Guard rule `roadmap-one-writer`").
- **Incident.** 2026-11-03 16:13 and 16:14 CST: session home-triage-4 (`local_9d699db2-43ff-46a7-8246-fe6c672330e1`), repo shivinate7/home, refused twice on a push to `roadmap`, the second after a `get_session` call. guard.log holds no other `roadmap-one-writer` line. The rule reached that Mac at 15:27 CST, when the install moved from 84a56038 to da8d8073.
- **Retire.** A local triage session proves its tier, and a local lane is still refused. A new test shows a local triage push refused on main (red) and allowed after the fix (green), and a local lane push refused in both.

## Brief for the fixing session

Fix the false refusal above, in claude-settings, as one lane with its own draft PR cut from main.

1. Read `docs/decisions/session-tiers.md` (the `roadmap-one-writer` bullets) and `merge-role-proof`, which the rule's tag read copies.
2. Pick a proof a local session can give and a local lane cannot fake by mistake. Candidates, in order: the `meta/page` `writer` of the repo's waiting page; the roster in CLAUDE.md on the record branch (project-ops); a role the coordinator records when it starts the session. Use the `get_session` fields a local session has: `sessionId`, `title`, `parentSessionId`. Name the pick and why in the decision record.
3. Test first: add the cases to the guard's tests and show them red on main. Cover a local triage push (allowed after the fix), a local lane push (refused), a cloud triage tag (still allowed), and no proof at all (refused).
4. Change `_own_tier_proved` or `record_writer_hit` until the cases go green. Keep the fail-closed reading for any read error.
5. Fix `RECORD_REASON` so a local session is told the step that proves it, never a retry that cannot pass.
6. Update the `session-tiers` bullet in place, and delete this debt record in the same PR.

Check that proves it done: the new cases pass, and `bin/verdict` runs the guard suite green. Report cap: 25 lines.
