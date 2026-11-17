# Lane archive-flow: handoff

Lane archive-flow (topic `archive-flow`, steps `handoff-lands-tracked-first` and `batch-runner-start-names-idle-lanes`), written 15:5x CST Nov 17.

## Landed
- #2917 (a lane may push its own handoff to the record branch): merged 14:04 CST Nov 16.
- #2817 (HOLD flag on idle lanes): merged 15:04 CST Nov 16.
- #2922 (batch steer: get_session in one message, archive in the next): merged 15:06 CST Nov 17.
- #2848 (decision `session-tiers`, brief and operating-model prose for the archive flow): merged 15:48 CST Nov 17, commit a752de196d9a.

## Notes for triage (not debts)
- `session-tiers.md` line 80 "Its every step has landed" clashes with "whatever its step status" (already on main).
- Some texts still say get_session "alone" (`git grep -n alone -- hooks merge`); no open step owns them.
- "ends with HOLD" (session-tiers.md and the merge.py docstring) should read "carries a HOLD: flag"; a HOLD-flagged joint line is still counted among lanes to archive (build.py, merge.py, roadmap SKILL.md).
- Lane lint cannot read the PR body (needs PR_BODY in the environment).
- `ARCHIVE_CITE` empty string passes the scanner; operating-model `<session-slug>.md` vs guard `<slug>-handoff.md`.
- The brief template has no room for an added line (main's generated brief sits at 491 of 492.6 words).
- A chained `git commit && git push` passes the guard when an earlier handoff commit sits in the range (not probed).

## Open
- Install refresh `merge/install_from_main.sh` was denied by the classifier; the coordinator routes it.
- Branch `archive-flow-prose-2` is archived at `archive/archive-flow-prose-2`; the branch itself stays on origin for the computer session to delete.
