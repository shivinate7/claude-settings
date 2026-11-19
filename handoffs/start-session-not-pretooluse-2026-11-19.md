# Handoff: lane start-session-not-pretooluse, 2026-11-19

- Slug: `start-session-not-pretooluse` (step of the same name, ruling `own-809-reopen-hook-card`, item 809).
- Repo: shivinate7/claude-settings. Parent: coordinator `session_013NEJL1gw6EdrSyvHkTUEx6`. Runner: `session_013NEJL2f1YCYsvLdpFqtWP3`.
- Branches (origin): `start-session-not-pretooluse` (PR 3381 head `cdb68f8d8d6a9457d1f0b08f67de35237d0bef6c`), `start-session-replaces-3381` (PR 3501), `start-session-not-pretooluse-tests`, `-tests2`, `-tests3` (test-author branches, merged into the PR branch).

## Open PRs

- None open. PR 3501 merged 2026-11-15 08:18 CST (REST, merge commit `5a0940f5ad97`, head `1312761607450b5f3cf466f7ef8faf70aeba41d4`). PR 3381 is closed, not merged; 3501 carries the same tree. Not re-read today.

## Done

- Option b chosen: `mcp__ccd_session__start_session` is out of every PreToolUse matcher in `settings.json`; a PostToolUse entry runs `hooks/start_session_audit.py`, which flags a start below the model floor or with the caller's handoff unread, and names the new session (`session_<id>`, else "id is unread"). Fails open.
- Decision `start-session-not-pretooluse`; debts `start-session-checks-after` and `start-session-load-unbraked`; doc rows updated.
- Tests: `lint/test_settings_matcher.py` (class `StartSessionNotPreToolUse`, red on old `settings.json`), `tests/guard/s38500-start-session-audit.py` (family `start-session-audit`, 26 cases).
- Review: round 1 haiku PASS (below its sonnet row), round 2 sonnet FAIL, round 3 sonnet PASS (net value negative), fix check sonnet PASS, then a fresh sonnet round 1 PASS recorded on 3501. Owner ruled "merge as is" (`own-3381-a`, 2026-11-15 01:43 CST).

## Unfinished

- Owner's fresh Bypass test on the desktop app with a Haiku start: unrun. Needs the owner's Mac. Item 809 closes only after it shows no card.
- Unknown: the app code path (owner's reading only); whether a PostToolUse hook on `start_session` raises the card; whether the start result carries a `session_` id; whether PostToolUse `additionalContext` reaches the desktop; whether `interrupt_session` / `archive_session` reach a desktop-made session.
- The decision file puts "This decision picks option (b)" under the owner's quote; b was the lane's pick. Unfixed on main.
- Four reviewer findings and my notes went to the coordinator and triage as notes; not pushed by this lane: audit SESSION_ID regex still names words like `session_started`; a string error result with a Haiku model is flagged as a start; an agent caller's flag names tools the guard refuses for agents; two debt files gloss the decision as "not gated" (glossary `gate`). Also unmeasured: `docs/records.md` rebuild before CI; whether a `start_session` lane carries the lane tag.
- Replacement of the lost checks (model floor, handoff-unread, load brake on a start) went to a follow-up lane the coordinator started.

## Next step

- The owner runs the Bypass test, then the coordinator or triage closes item 809 or reopens it.

## Refused acts

- The merge tool refused a round 1 only record on PR 3381 as a review restart. The coordinator's route, a `Replaces #3381` PR, was taken (3501).
- The builder was refused a test-file conflict edit; a test-author did the merge.

## Owner rulings held

- `own-809-reopen-hook-card` (2026-11-14 00:12 CST): remove the matcher, keep the checks some other way, say which and what is lost.
- `own-3381-a` (2026-11-15 01:43 CST, item 865): merge as is.
- Coordinator's order 2026-11-19 00:24 CST: wind down, hand off, push an archive branch.

## Agents (all finished; none running)

- Test-author (haiku), branches `start-session-not-pretooluse-tests`, `-tests2`, `-tests3`.
- Builder (sonnet), branch `start-session-not-pretooluse`; a third-try builder (opus), same branch.
- Reviewers (haiku round 1; sonnet rounds 2 and 3, fix check, and final round 1), read only.
- Merge test-author (haiku), pushed the merge of main on `start-session-not-pretooluse`.
