# Handoff: lane sim-lease-gaps

Written 2026-11-19 00:2x CST on the coordinator's wind-down order (00:24 CST, owner's 00:19 CST order via the consultant).

## Identity

- Slug: sim-lease-gaps. Repo: shivinate7/claude-settings.
- Goal: close the sim-lease and sim-test gaps the Mac sim gatekeeper found, as one draft PR. Source: consultant relay 00:20 CST Nov 15, step sim-lease-gaps; owner pick 336 a (a reuse takes the lease).

## Open PRs

- #3482, draft, open. Branch `sim-lease-gaps-fresh`. Head 833682e143bc2c9deaebbc384c2fbdbda0b6d6ad (GitHub REST read 00:26 CST Nov 19). `mergeable_state` dirty: conflicts with main (main a549f0d85).
- Earlier heads: c3bc3d239 (code commit), 0dfed5f2f (my last fix push). My own commits: test commit 1edc4507f, code commit c3bc3d239, fix 0dfed5f2f. I did not re-trace the commits above 0dfed5f2f in this file: unknown.
- Replaced: #2787 (closed by runner 10, pointer comment 6891957419), #1599 (closed).
- Review records on #3482: 6892010024 (head c3bc3d239, round 1 sonnet FAIL), 6892012314 (head 0dfed5f2f, round 1 FAIL plus fix check sonnet PASS). Both name older heads, not the live one. Lane lint comment 6893715063: PASS at 0dfed5f2f; guard 286, guard-b 285, guard-c 285 mutants killed.

## Done

- Gaps 1 to 3 (a reuse takes a lease; two runs never hold Duo 1; a stopped run restores appearance and fold): tests red on main ef36c765d (14 of 46, 9, 30 failures), green on the branch. `REUSE_KEY` is the one home of the `reuse` key; guard and mutants read it.
- Gaps 4 to 7: a record each. Gap 4 needs Mac load data (Mac read: 26 crash reports, loads 41.16, 30.58, 19.22). Gap 5 is step sim-lease-load-brake's work (draft #2899, ruling sims-load-brake-only). Gap 6: first-come order stays, 1800 s holder limit unbuilt (coordinator pick, undoable). Gap 7 waits on a decision (debt sim-holder-session-gone).
- Docs: sim-lease-tool and sim-test-is-the-one-boot-path decision records, ios-apps skill, README, five debt files.

## Unfinished

- Plain merge of main into #3482 (own-draft-rebase-lanes). Planned after fix #3681 merged (main's CI was red from two stale mutation anchors). Suspended by the wind-down; whoever takes the PR does it.
- Hand the new head to runner 10 and ask whether the merge tool accepts the two records; if not, hand in what it printed. Do not retype a record.
- The Mac-only step (one `{powershell: n/a, mac}` command) went to the coordinator for triage. The first command used `~/claude-settings`, which does not exist on the owner's Mac. Its fix is the coordinator's call.
- The guard-b CI failure did not reproduce here (285 of 285, 641 s); runner 10 said its disk ran out. Cause unmeasured.

## Next step

Merge main into #3482, push, hand the head to runner 10. I do not mark ready or merge.

## Refused acts

- `merge --lane-lint` and long background commands are refused in worktree sessions; runner 10 runs lane lint from outside a worktree.
- A hand-made worktree was refused; use EnterWorktree.
- A review record naming the full model id for a fix check was refused (wants `sonnet`).
- Not covered by my grant: marking ready, merging, force push, closing a PR, erasing a shared device, a runtime or Xcode change, any act needing the owner's Mac.

## Owner rulings held

- 336 a (12:31 CST Nov 7): a reuse takes the lease. Home: decision sim-lease-tool, ruling 4.
- sims-load-brake-only (21:59 CST Nov 12): no hard-coded sim count; slot rules live in step sim-lease-load-brake.
- Nothing waits on the owner.

## Triage notes (sent in the hand-in)

REUSE_KEY comment placement in `bin/sim-lease`; dead `SIM_LEASE_MAX` env in tests; unmarked counts in the `bin/sim-lease` and `bin/sim-test` headers; weak case 78 and 135 assertions; case 66 flake; duplicate `loads()` in `hooks/sim_boot_record.py`; case 105 fixed sleep. Queued guard idea, no step id: a check that a handed-over command's first `cd` path exists.

## Agents (all finished; none run)

Names only; each worked in its own worktree and none left a branch of its own that I know of.

- Round 1 reviewer sonnet `a4b9c5c4ffa24a426`; fix check sonnet `a2c735a362957f8ae`.
- Shard builder `ac671e73961b71cf6`; lint-repro builder `ace1554a299aff0ab`.
- Earlier reviewers: `ab98d30164633f267`, `acb4c5c660a04189f`, `a7f4168ce102fad6c`, `adf000361391bc84d`, `add7c650854ee7756`, `ab590eb66c0436750`.
- Handoff audit Explore sonnet `aedc42d398f8edb73` (this wind-down).
- Local worktrees: `.claude/worktrees/sim-lease-hang`, `sim-lease-docfix`, `sim-lease-shardb`, `handoff-sim-lease-gaps`.
