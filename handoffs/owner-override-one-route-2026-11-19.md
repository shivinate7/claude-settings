# Handoff: lane owner-override-one-route (written 2026-11-19 00:35 CST)

Order: coordinator relay 00:26 CST Nov 19 of the owner's 00:19 CST order (wind down, hand off, archive). Relayed, not typed by the owner to this lane.

## Identity

- Slug: owner-override-one-route. Role: lane (session-tiers). Session: session_013NEJL1ymdMFYoj4wQG9oUR. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Hand-ins went to runner 10, session_013NEJL2f1YCYsvLdpFqtWP3.
- Goal: one override route. The owner's typed words are judged; `override` with any length form is the timed fast path with no model call; each grant prints one receipt line; a non-owner prompt grants nothing. Source: coordinator brief 11:19 CST Nov 12 (owner R12, 16:10 CST Nov 10; Q1, 09:10 CST Nov 11).

## Open PRs (read from the GitHub REST API, 00:30 CST Nov 19)

- #2850 (PR 1), branch `owner-override-one-route`, base main. Open, draft, mergeable_state dirty. Live head `324b01996e7b04484d61cd0e0e18cda3bd8adc54`: a merge of main made by another session (session_013NEJL4Rvnn8Mk8f7NnBGs, 19:38 CST Nov 15, two conflicts resolved by hand). Not my work; lint and review record at that head are unread. My last head was `e372280decba27134391c77571f204de9a88fdcc`: lane-lint PASS, touched-tests green, `merge --reviewed` read "done: round 1 is FAIL, and the fix check passed" on stable 22231dd779c1 (22:51 CST Nov 13).
- #2928 (PR 2), branch `owner-override-opus-route`, base = branch `owner-override-one-route`. Open, draft, mergeable_state dirty. Live head `80b400bc605795e0fe457becf0334c54efb18910` (unchanged since my hand-in). lane-lint PASS, touched-tests green, `merge --reviewed` read done (same line) at that head. Its base moved: #2850's head is now 324b01996e, so a merge of that into this branch is owed before it can join.
- Neither is merged. Both were handed to runner 10 and the coordinator at 22:51 CST Nov 13. Runner 10 had not merged them when I last read.

## Done

- BUILT #2850: fast-path `override <length>`, source and record gate, one receipt line, fast-length check that ignores a length inside a pasted block or code span, bare-number test rows, decision `owner-override` rewritten in place.
- BUILT #2928: Opus keyword gated like the override keyword; plain Opus ask lifts only the session's own spawns until the owner's next typed prompt or 2h (turn file); `opus <time>` timed; `opus off` ends any grant; a one-act override ends at the owner's next typed non-grant prompt; decision text cites own-783-b.
- RECORDED: review records as PR comments on both PRs (tool form: #2850 6870837215 and 6871000298; #2928 6870421218 and 6871068348), plus older hand-posted records.

## Unfinished

- Merge: #2850 and #2928 never merged. Both conflict with main now.
- Unknown locally: full `hooks/test_guard.py` and `hooks/mutate_guard.py` (CI runs both). `docs/records.md` stale (merge tool rebuilds it). Census rows H10-H12: unknown, no file found.
- The agent-end read (Opus grant ending when its agents end) is lane agent-end-read-in-hook's, not built here.
- Notes in docs/debts/notes.md: end-turn and end-once silent on a failed removal; peer-origin ask grants. Round-1 owner questions never answered: the receipt names no lift (R12); trailing `?`, a negation or `off` after a length goes to no judge.

## Next step (for whoever resumes)

1. Fetch #2850; read its head 324b01996e; run `bin/verdict bin/merge --lane-lint 2850` (bare, background) and `bin/verdict bin/merge --reviewed`; hand in again if it reads done (a clean merge of main needs no fix verifier).
2. Merge #2850's head into branch owner-override-opus-route (plain merge, no force); re-lint #2928; read `--reviewed`.
3. Merge #2850 then #2928 with the merge tool, under every merge check.

## Refused acts

- None blocked a deliverable. Guard refusals were met by fixing the brief (model field on spawns, probes for claims about main, bare `verdict`). No override was granted or used. No `--lint-unknown-ok`.

## Owner rulings held (all relayed; homes in decision `owner-override` and `agent-model-cap`)

- R12 (16:10 CST Nov 10) and Q1 (09:10 CST Nov 11): the one route and the source and origin gate.
- Item 601 a (12:54 CST Nov 12): one-act override ends when spent, on `override off`, or at the next typed non-grant prompt. Its Opus half is superseded.
- own-761-d-task-scoped-opus ("agreed" 14:21 CST Nov 13): plain Opus ask grants only its own agents; target is "ends when those agents end".
- own-783-b-interim-narrow-end (19:21 CST Nov 13): until the agent-end read works, the grant ends at the next typed prompt or 2h, own spawns only.
- R9 reading (owner 18:35 CST Nov 13, relayed): a passing round or passing fix check ends review; live in the merge tool on stable 22231dd779c1.

## Agents (all finished; no agent running)

- test-author: red rows for the fast-length false alarm and for the bare-number branch; pushed to `owner-override-one-route` (commits 4cc6eac14e, 83422d77cf).
- builder (sonnet): fast-length fix 81b6c45586; D1, dead `WORD`, docstring fix e372280dec.
- record-writer: own-783-b citation 822de235e8; merges into `owner-override-opus-route` 48a8117080, 80b400bc60; doc commit 5c6cc3ed72.
- reviewers (sonnet, plus haiku in older rounds): round 1 on #2928 and #2850; fix checks on both. Worktrees are local to the old container and gone; branches above hold all pushed work.

## Files

- Code: hooks/override.py, hooks/local_time.py. Tests: hooks/test_local_time.py, tests/guard/s36421-override.py, hooks/test_shared_names.py. Docs: docs/decisions/owner-override.md, docs/decisions/agent-model-cap.md, docs/debts/notes.md, docs/catalog.md.
- Local handoff of the live session: /root/.claude/handoffs/84cbaa40-70b7-5805-9ff1-4572c5fac06e.md (outside git).
