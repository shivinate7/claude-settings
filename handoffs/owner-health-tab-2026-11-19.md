# Handoff: lane owner-health-tab

Written 2026-11-19 00:30 CST by the lane session (session_013NEJL4QMYAUC7dm23GmXbx), on the coordinator's wind-down order of 00:26 CST (owner order 00:19 CST, relayed by the consultant).

## Identity

- Slug: owner-health-tab. Role: lane. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6.
- Step record: branch `roadmap`, `roadmap/data/steps/owner-health-tab.json` (read, never written by this lane).
- Goal: a "Health map" tab on the claude-settings page shows what the owner sees, what makes it happen, and how healthy each part is (table: what you see | grade | why), plus a check that lists each hook, check and skill no row names.

## Open pull request

- #2904 (draft), branch `owner-health-tab`. The lane pushed head a02ae3fbf. Read live at 00:29 CST: head 67e8dabe1, 72 commits, state open, draft, mergeable_state dirty. Someone else moved the head after the lane's hand-in. This lane did not push it.
- Review record posted by the lane for head a02ae3fbf: comment 6834444527. It reads: Guard or check yes; check rounds 1 to 3 and design reviewer rounds 1 to 3, all FAIL; net value positive. The tool refused a Fix check line (the PR opened at the final head). The record is stale for the moved head.
- Lane lint on a02ae3fbf: PASS (322 s). Not re-run on 67e8dabe1.

## Done

- `lint/check_health_map.py` (new check, exits 0 on the real repo: "covers all 101 parts" at a02ae3fbf), with tests `lint/test_check_health_map.py` (red first, mutants proven) and its own CI step.
- `docs/health-map.json`: 20 rows from the retrospective's Nov 11 draft (read of main c85a832e2), each with `covers`, `gold`, `quiet`; row 12 (spend) is `no_part`.
- `skills/roadmap/build.py` bakes a `healthMap` key into the roadmap block; `skills/waiting-page/page.html` draws the third tab "Health map" (worst first, target column, exhaustive line, janitor and merge kinds, tab bar wraps without sideways scroll).
- Mockups and notes: `docs/design/health-tab.html`, `docs/design/health-tab-notes.md`.
- Two notes filed in `docs/debts/notes.md`: `health-map-broad-family-glob`, `health-map-star-py-glob`.
- Reviews: check rounds 1 to 3 (reviewer; round 1 ran haiku, rounds 2 and 3 sonnet), design reads 1 to 3 (design reviewer opus), fix verifiers PASS on aa30acec9 and 121ee8eda (reviewer sonnet).

## Unfinished

- Grades and figures are the Nov 11 draft with their read date. A per-row on-demand re-measure is not built. Only the exhaustive count reads live. The step asks for on-demand grade reads, so this part is open.
- Two rows are stretched to fit (spend has no part; plumbing parked on rows 6, 14, 16, 19).
- Latent gaps: .js, .ps1 and .cmd hooks and subfolders are not scanned by the check.
- The page says "no map yet" only when the build reason is "No such file or directory" (fragile).
- Page tests ran on Playwright 1.63 locally; CI pins 1.64.1.
- Mockup `docs/design/health-tab.html` line 109 still has the old wrap rule (the file is a drawing).
- The PR head moved to 67e8dabe1 and is dirty: needs a look by the runner, not by this lane.

## Next step

Batch runner 10 reads #2904 at its live head (67e8dabe1). It decides whether the posted record counts, runs `merge --lane-lint 2904` and `merge --reviewed`, and resolves the dirty merge state. A fresh fix verifier is owed on any head the lane did not review (decision `pr-review-record`).

## Refused or unrouted acts

- The merge tool refused `--fix-check` for a lane PR opened at its final head. The lane did not route around it; the point went to the coordinator.
- No other refusal is open.

## Owner rulings held

None of the lane's own. The coordinator relayed these (coordinator, 11:36 CST Nov 12): third top tab; keep the Records Health card; the tab is named "Health map"; build the target column; sort worst first; phone cards not folded; no mods in the coverage count; unknown ring unchanged. Their home is the coordinator's record and this file; they have no tracked decision.

## Agents (all finished, all local, nothing pushed by any of them)

- designer (opus): branch worktree-agent-a06f0b4c982a17687, mockup commit ecaf07a0f.
- test-author (sonnet, id ac1df5107a1ddb4d9): worktree branch worktree-agent-ac1df5107a1ddb4d9; branches health-map-rulings, health-check-mutants, health-tab-tests, health-design-red, health-read-fix, health-tabs-red, health-tabs-slack.
- builder, check (sonnet): branch worktree-agent-ab1c40c9e7e2dcde1, head 4c989ff06.
- builder, tab (sonnet): branch worktree-agent-aa4500874ed80753f, head 4496d2064.
- builder, integration (sonnet): branch owner-health-tab-int, head 1f44147be.
- builders, fixes (sonnet): owner-health-tab-final (aa30acec9), owner-health-tab-design-fix (3f33e5fe7), owner-health-tab-final2 (457767808), owner-health-tab-final3 (121ee8eda).
- record-writer (sonnet): owner-health-tab-final4, head a02ae3fbf (this is what was pushed as `owner-health-tab`).
- reviewers (sonnet, one haiku in round 1) and design reviewers (opus): read only, no branch.

These local branches live in the cloud container's worktrees and are lost with it. The pushed record of the work is `owner-health-tab` on origin and PR #2904.
