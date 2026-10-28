# c122-option-diffs

Branch c122-option-diffs (base main a64166ae). Lane started 2026-10-28.
- Designer (opus) drawing items 2, 3 and open page-review fixes.
- Test-author (sonnet) writing red tests for the four small c100 defects.
Next: builder after design; then reviewer and design reviewer; draft PR.
- Test-author done: 3 red tests (partial-Undo "and" list, failed Undo names every item, failed receipt delete clears state) on worktree-agent-aadaff10553f9dfd3 8bb7ddd.
- Deferred: why — "empty tiers hide their empty line" is today's intended behaviour (page.html renderList and rail skip an empty tier; test "rank never moves an item across tiers" asserts it). Departs from: current behaviour. Question for shiv: should each empty tier show an empty line in the list, the rail, or neither? Lane keeps current behaviour meanwhile; not blocking.
- Designer done (cc513f0, docs/design/waiting-page*). Merged with tests into lane head 46cdc87. Builder (sonnet) building 1A differs, design state deep-link, short titles, 3 defect fixes. Items chip/pick-names/digit/sparkle already on main.
