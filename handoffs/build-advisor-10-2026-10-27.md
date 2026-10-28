# Hand-off: build advisor (10), claude-settings, Oct 27 (ends 23:13 CDT)

Tally at hand-off: 12 messages to the coordinator, 4 to shiv, 6 dispatches of 12.

## Rulings
- Usage freeze (shiv, Oct 27 13:31 and 13:32 CDT; cmsg_01DoF7thf3iq2Srr1UsfXgh2DhVeWxLo5gce39C6Hvi7b8, cmsg_01DoF7thf3iq2Srr1UsfXgh298P1q4zbW9zZzzhVAbjmi9): 10% plan usage left. Land only critical work that is near done. Pause the rest, each lane committed and pushed with a hand-off. Delete and close nothing. Hold until main is stable and the bandwidth is assessed. Its only home is roadmap/outbox/build-advisor.md; triage has not filed it. #723 landed under it, because it held only lanes that were already green and reviewed. Whether the freeze is lifted is shiv's call (asked Oct 27 23:11 CDT).

## Main
- e0f9e2d (#723, merged 16:55 CDT). CI passed on main at 17:25 CDT (per shiv's 23:11 check). 11 required checks.
- Landed today: #704 (c130, o8 lane 6), #711 (c127 part 1, c133, c77, read-race fix #707, o4 scorecard), #723 (c54 pin order, no-gap read race #712, c134, c137 unshallow #719). Other sessions merged #717 (ios-apps hinge), #713 (waiting-page option mockups) and #701 (degen colour) during the freeze. Each one moved main and forced a batch re-run.

## Open PRs and parked lanes (all drafts; nothing deleted)
- #715, c95 step 1a (the full CI run stops timing out): branch claude/project-thread-9gwusu af9d9d6e, based on 9264397. Green and reviewed. It adds the required checks gates-guard and gates-windows-sweep to .github/stamp.json. Branch protection must add them in the same merge act.
- #721, c95 step 1b (which tests catch a planted bug): branch c95-test-value 51e56c90. Review round 1 was clear. It conflicts with main only in docs/debts/notes.md; keep both sides' lines.
- #720, keep build folders while a process runs: branch claude/project-thread-1jt01d 1ea149de. Red twice. In #718: a stale mutation anchor (since fixed). In #722: the two old build-dirs mutants survive with 0 red ("a folder with a live process cwd inside is renamed", "a trash name with a live process cwd inside is deleted by the reap"). Fix: tests or re-pointed anchors in janitor/mutate_sweep.py, then one review. It has no roadmap step yet; note at roadmap/outbox/stop-cleanup-live-builds.md.
- c126 + d9 with c131: branch claude/project-thread-xczmrz b41fb51, no PR open (it was in batches #710 and #716). Red twice on skills/waiting-page/tests/page.test.mjs test 88 at 390 wide ("the mockup is cut: 9 to 399", then "9 to 414"). The lane's refit-on-show fix did not hold on CI. Fix the page, never the test. Brief: briefs/c126-fix-viewer-after-c130.md. Its cause note says c130 was not the cause.
- #639, o13 lane A (gate/try rename): far behind main. The o13 brief says to redo it on a fresh branch and close #639.
- c142 (rounds 2 and 3 reviewers run Sonnet): paused, hand-off 88f9b27. No code yet. Brief briefs/c142-reviewer-round2-sonnet.md.
- d4 (Banchi phone design, blind): paused, hand-off a6bb03f (handoffs/d4-banchi-phone-2026-10-27.md).
- c143, c138, c139, c140, c144, then c122, c135, c136: ready on triage's list. Not dispatched (freeze). c143 builds on o4's scorecard, now on main. c122 waits for c126.

## d9: not on main
d9's commits (b7a33ff3 "a design pick shows a picture of each option", 89b88d2e layout) are only on the parked c126 branch claude/project-thread-xczmrz. The d4 hand-off is wrong where it says d9 is on main. Main does hold #713 (waiting-option-mockups, "a mockup inside each option card"), which overlaps d9's option-card picture. The c126 lane must merge main and reconcile with #713 first. #713's test changes are a likely cause of its viewer red.

## Merge steps (merge.py)
1. Build the batch on current origin/main: `git checkout -b batch-<slug> origin/main`, then `git merge --no-ff --no-edit origin/<lane>` for each lane. Resolve conflicts that only add notes lines by keeping both sides.
2. Push. Create the PR with `gh api repos/shivinate7/claude-settings/pulls -F draft=true -F body=@file` (GraphQL is 403), then POST .../pulls/N/ccr/ready_for_review. Subscribe to the PR. Set a check-in about 55 min out: the macOS jobs queue for runners, and a run takes 50-60 min.
3. On green: `python3 merge/merge.py N --confirm`, run in the checkout, with no pipe or redirect. It needs an unshallowed clone (`git fetch --unshallow origin`). It refuses a head that lacks the current origin/main, so main moving forces merging main in and a re-run. If the lock release fails on auth, run `python3 merge/merge.py --unlock`.
4. Close the lane PRs as replaced: `gh api -X PATCH .../pulls/N -f state=closed`. GitHub may show a lane PR as "merged" once its head is on main (#714 did); that is not a separate merge.
5. Red batch: read the failing job and drop the lane whose files it touches. Rebuild on main under a new branch name, never revert. Close the old PR with one comment.

## Gotchas
- The guard refuses `git pull -q` and `git push -q`. Use `2>&1 | tail -1`.
- The local unittest suite runs (`bin/verdict python3 -m unittest ...`). pytest is not installed in the cloud container.
- shiv flagged a possible install.sh bug at line 632: in a cloud install, the refresh hook replaces all start-up hooks, so cloud sessions lose the hand-off hooks. Unchecked; not filed.
- Steps marked done on the roadmap at c2f9668d: c133, c77, c134, c137. c130, c127 part 1, c54 and o4 got notes only; c130 should be marked done.
