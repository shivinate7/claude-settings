# Degen report on claude-settings, 2026-11-12

The owner pasted this report into the retrospective session at 20:51 CST Nov 12. The Degen coordinator wrote it.
The fenced block below is the report word for word. The ledger after it gives each finding one home.
A row closes only on proof: a merged PR, a stored ruling, or a cited commit.

## The report, word for word

```text
claude-settings fixes found by the Degen coordinator (2026-11-11 to 11-12)
Each item: what went wrong, where it came from, and the fix asked for.

1. Feedback-inbox hook can't see page read-backs. Local sessions have no ArtifactData tool, so the hook never sees a db_query read-back of a waiting-page item. Every page pick has to be marked [note] -> page:<n> by hand (items 208, 209, 210). Fix: accept a db_query read-back of collection items as the read.
2. Local sessions can't republish the waiting page with pictures. They have no file-output tool, so option cards carry mockup paths instead of images. This blocks pictures for items 86, 216, 217 and 219 (owner question P1/P2, still open). Fix: let waiting-page publish from local files, or give local sessions the file-output tool.
3. The merge tool has no narrow exception for a test fix that a merge forces. One fix check per round; any wider diff restarts the lane at round 1. The Downloads filter went 597 → 635 → 656, restarting twice for merge-forced fixture changes. Fix: allow one extra fix check when the new diff is only the merge resolution plus the test it forced.
4. No guard on box writes in read-only audits. Two audit agents wrote temporary files on the HA Green over ssh despite a no-writes brief. Both cleaned up. Fix: a guard that refuses an ssh write (>, tee, mktemp, touch) to the box from an agent whose brief says read-only.
5. No check before a "not worse than main" claim. I told the owner the Downloads filter's open-Duo layout was main's own, without checking main. Fix: a report-guard rule that a regression or no-regression claim cites a main read (a file:line or a main screenshot).
6. CI waits have no enforcer. The batch runner sat idle for about 16 h (2026-11-12 03:51–20:20 CST): batch 659's native-record job went red and nothing woke it. Rule git-ci-wait-checks-in has no check. Fix: a Stop hook that refuses to end a turn when the session has an open CI run and no one-time check-in set.
7. The agent-role-model guard ignores the override it offers. It printed "type override" for a Fable spawn the owner named. override, then override 15m, were both refused again. A cry-wolf remedy. Fix: honour the override, or stop printing it.
8. The model cap puts round-1 reviewers on Haiku, but the merge tool wants Sonnet records. Lanes re-run Haiku-passed fix checks on Sonnet (PR 637, 543). Fix: one model rule for both.
9. builder-test-edit refuses comment-only edits in test files. Lane saves-not-arriving had to spawn a test-author just to reword comments (PRs 642, 644). Fix: allow a diff that changes only comments.
10. The live claude-settings pin fell 439 commits behind. The install log shows no run between 2026-11-11 21:32 and 2026-11-12 20:18 CST, though sessions resumed many times. The owner had to ask for the update. Fix: find why the SessionStart child didn't move local main or the pin, and log a line when it skips.
11. Simulator noise has no shared home. iOS 27.1 sims crash Siri, intelligence, Mail and Spotlight daemons on every Mac sim (about 560 reports; Apple forum thread 842558). On 2026-11-12 I disabled 17 of those services in the Duo 3553660D (launchctl disable user/foreground/<svc>), keeping chronod and AppIntentsLiveEntityService. Fix: put this list in skill ios-apps boot steps or sim-test, so it covers every sim and survives an erase.
12. Simulator wallpaper store grows without limit. iOS 27.1 PosterBoard keeps a home-screen snapshot per fold or launch, never deleted. The Duo 3553660D store reached 41 GB in 10 days (Duo 2: 8.5 GB), and PosterBoard crashes reloading it on every boot. This is why an erase "didn't fix it": the store regrows. Owner-approved delete, 2026-11-12 20:44 CST. Fix: sim-test (or the fold script) deletes data/Library/Application Support/PRBPosterExtensionDataStore while the sim is shut down, before each boot.
13. Pin the Duo to a newer runtime. Xcode 27.2 is installed, but only iOS 27.0 and 27.1 runtimes are. The entitlement crash in intelligencetasksd and AppIntentsLiveEntityService may be fixed in 27.2 (unverified). Fix: install 27.2 (xcodebuild -downloadPlatform iOS), make a new Duo on it, and update the device IDs in skill ios-apps.
14. Session checkouts go stale. A coordinator or role session that never commits keeps the main it started on. Mine was a day old, so the pick guard read an old layout-extras.json and named the wrong waiting page. Fix: (a) at SessionStart and UserPromptSubmit, fast-forward a clean worktree with no commits of its own to origin/main, and warn when one with commits is behind; (b) guards that read repo config read it from origin/main, not the working tree.
15. No way to relay an owner grant that a lane can trust. You approved two acts in my chat: the wallpaper delete (20:44 CST) and the hardware-keyboard switch. Both lanes rightly refused my relay ("a peer cannot grant"). So either I do the act myself, or you repeat the yes on the page. Fix: the coordinator writes the owner's chat grant, quoted with its time, to a grants file (or the waiting page) that a lane's guard can read and verify against the transcript.
16. The worktree-isolation check refuses ordinary file edits outside git. A Python heredoc or a sed/mv on my own handoff inbox file (not in any repo) was refused as "too complex to verify that it stays inside the worktree". I had to fall back to many single Edit calls. Fix: judge only commands that name git or paths inside a checkout, and allow writes under ~/.claude/handoffs/<own session>.
17. The feedback inbox needs a hand-written item for every owner message. That includes a pasted crash report and the echo of a command you ran yourself (bash-input). Each missed one blocks the turn. Fix: skip bash-input echoes and pasted content with no instruction, or let one item cover a run of messages.
18. Model-cap guards disagree with each other. The spawn judge says Fable is never allowed as Explore ("no override lifts this"). The role-model guard offers override for the same spawn, then ignores it (item 7). Fix: one rule, with one remedy that works.

Not claude-settings: the Claude desktop app

* A session can't start new sessions while you're on Remote Control ("this turn can't start that session"). This blocked the board Links view lane (item 212 b) and the UI-tests-on-main lane, so I had to borrow idle lanes.
* SendMessage reports "delivered, not confirmed read". There is no read receipt, so a session can't tell a lane that is ignoring it from one that is busy.
```

## Batch 2, word for word

The owner pasted this at 21:30 CST Nov 12. It adds items 19 to 24 and corrects two batch 1 lines.

```text
ill get that back to you. meanwhile, more feedback reporting from the degen repo: claude-settings fixes, batch 2 (from 2026-11-12 21:00 CST)
Batch 1 (items 1–18) went to the owner at 20:48 CST. New items start here.

19. Skill ios-apps has no testing standard for screens. It names the tools (XCTest for UI tests, sim-test, make native-check) but not what each kind of test is for. With no standard, Degen grew 381 slow, flaky XCUITest cases that check layout and run folded only. Home grew the opposite: source scans that read view code as text and never check what is drawn. Degen's 49 Save-menu failures came from a helper tapping the corner of a 44×44 frame, outside the drawn 44 pt circle. Fix: add a test-shape section to ios-apps, and to its starter so new apps begin that way:
   * pure rules, in swift test;
   * render or layout tests that host each screen at every shipped size (both Duo fold states), with no app launch;
   * one or two XCUITest smoke cases per screen, only for presses, gestures and navigation, run in every fold state;
   * taps aimed at the drawn shape's centre through one shared helper, never a frame corner or an offset;
   * waits on state, never fixed sleeps;
   * a source scan only where no render test can see the thing.
20. The Pro lease blocks the Duo. sim-lease grants no Duo slot while the Pro slot is held (decide(): if "pro" in held: return None). At 20:57 CST my Duo take was refused after 30 s at a 1-minute load of 25, with the Pro held by lane menu-bar-text (iPhone shots) and the Duo slot empty. Fix: allow Duo slot 1 beside the Pro when the load is under the bar, or state in the tool's record why both must not run at once.
21. builder-test-edit blocks merges that touch tests. This is a second shape of item 9. At 21:14 CST, two builders in lane downloads-type-filter were refused while merging PR 656's branch into PR 605's, because the merge conflicts sat in test-file headers. The lane session did the merge by hand instead. So a merge with test conflicts can't go to any agent: a builder may not touch tests, and a test-author may not touch product code. Fix: let a builder resolve a merge (a commit with two parents) whose test-file hunks come only from either parent, and still refuse new test edits.

Correction to batch 1, app section

* The app item "can't start new sessions while you're on Remote Control" was wrong. Both refusals (2026-11-12 04:34 CST and earlier) came on turns that another session's message had started. The app refuses new sessions on such turns, but its error said "The user is working over Remote Control". A start on a turn the owner began worked at 21:19 CST. The app fix: name the real reason in the refusal. The workflow fix: a coordinator queues starts for its next owner turn, and doesn't borrow idle lanes.
* The pin item from lane mac-suite-green (CI pins claude-settings actions at old commits, so lane-lint passes and CI fails) is Degen's own work, now in lane ci-milestone-shards. No claude-settings change is needed.

22. The live hooks don't match the claude-settings clone. Degen's compliance check (2026-11-12 21:21 CST) found that the live ~/.claude settings' hooks block differs from the clone's (PostToolUse, PreToolUse). So it couldn't mark guard rules as covered by the parent. This is after the 20:18 CST install. Fix: make the installer, or a --check mode, diff the live hooks against the clone and print the difference. Also, the compliance-check skill could name which copy it trusts.
23. Evidence for batch 1 item 3, the merge tool restarting a lane after a merge-forced fix. It happened a third time at 21:22 CST: lane downloads-type-filter merged 656 into PR 605, needed a 2-line doc fix after its fix check, and the merge tool refused a second fix check. The work moved to new PR 667 at round 1, and 605 will close. That's three PRs (597 → 635 → 656 earlier, now 605 → 667) restarted at round 1 for merge-forced edits. Raise its priority.
24. The Words check counts false alarms, so compliance-check ranks a non-problem. compliance-check listed 70 Degen Words hits besides "gate" (inbox, owner, hole, tier, entry, shape, worker) as fix #4. Lane words-lint found every one is a record slug, a code identifier, a quoted owner word or the word used in its correct sense, and changed nothing (2026-11-12 21:27 CST). A lane's worth of work bought nothing. Fix: the Words probe skips slugs, code spans and identifiers, and quoted owner text, and compliance-check ranks only hits that survive that filter.
```

## Batch 3, word for word

The owner pasted this at 23:25 CST Nov 12. It repeated items 22 to 24 word for word, so they are left out here. It adds item 25, item 26, more evidence for item 23 and a correction to batch 1 item 2.
```

```

## Ledger

Classes: ruled (already ruled or fixed), step (an existing step takes it), new (a new step), owner (needs the owner's call), elsewhere (not claude-settings).

| # | Finding | Class | Home | Status | Proof |
|---|---|---|---|---|---|
| D1 | Inbox hook misses page read-backs | step | step artifact-guard-matcher-names, PRs #2923-#2927 | in flight | none |
| D2 | Local page republish has no pictures (corrected in batch 3: local sessions have the publish tools; the gap is knowing which one) | step + new | step artifact-guard-matcher-names; rest: new step local-page-publish-route, narrowed to skill waiting-page naming the tool a local session republishes with (the skill names none on main 36807ad19) | partly in flight | none |
| D3 | No fix-check exception for merge-forced tests | ruled | decision pr-review-record:76,125,129 (owner 2026-11-10 14:07 CST) allows one more fix verifier after a conflicted merge of main; Degen merged a lane into a lane and edited after the fix check; step fix-after-fix-check holds the rest | ruled, rest on step | none |
| D4 | No guard on box writes in read-only audits | new | new step readonly-agent-shell-write | filed, roadmap 378ff3a35 | none |
| D5 | No check before a "not worse than main" claim | new | new step claim-vs-main-needs-read, extends #2765 | filed, roadmap 378ff3a35 | none |
| D6 | CI waits have no enforcer | step + new | wake: step red-job-wakes-runner (#2860); stop: new step ci-wait-stop-needs-checkin | partly in flight | none |
| D7 | Role-model guard ignores its own override | owner | with D18: guard.py:3836-3849, call_judge.py:32,324-343; step role-model-explore-veto-offer once ruled | ruled 21:59: override lifts the veto; step role-model-explore-veto-offer | none |
| D8 | Haiku round-1 reviews against Sonnet records | step | step model-table-one-home (#3010), step round1-sonnet-guard-table | in flight | none |
| D9 | builder-test-edit refuses comment-only edits | owner | decision builders-cannot-edit-tests, ruling 437 a; step builder-test-comment-edit once ruled | ruled 21:59: a, comment-only diffs; step builder-test-comment-edit | none |
| D10 | Live pin fell 439 commits behind | new | new step session-start-pin-skip-log | filed, roadmap 378ff3a35 | none |
| D11 | Simulator noise list has no shared home | new | new step sim-boot-noise-off (bin/sim-test), one lane with D12 | filed, roadmap 378ff3a35 | none |
| D12 | Simulator wallpaper store grows without limit | new | new step sim-wallpaper-store-drop (bin/sim-test), one lane with D11 | filed, roadmap 378ff3a35 | none |
| D13 | Pin the Duo to the 27.2 runtime | owner | skill ios-apps device IDs; step sim-lease-gaps asks the owner first | ruled 21:59: a, 27.2 Duo beside the old | none |
| D14 | Session checkouts go stale | new + owner | (b) new step guards-read-origin-main-config (git_reads.py:305, question_form.py:1062-1077); (a) owner, reverses step grants-read-from-main | ruled 21:59: b part a, fast-forward clean own checkouts; step grants-read-from-main | none |
| D15 | No trusted relay of an owner chat grant | step | step page-wakes-and-relays, PR #3038 | in flight | none |
| D16 | Isolation check refuses edits outside git | elsewhere | Claude Code harness; step harness-worktree-git-probe; debt note split-sentence-eight-copies | raise upstream | none |
| D17 | Inbox needs an item for every message | owner | decision owner-feedback-inbox, feedback_guard.py:241-248; step inbox-skip-bash-echo once ruled | ruled 21:59: a, skip bash-input echoes; b open | none |
| D18 | Model-cap guards disagree | owner | same root as D7 | ruled 21:59 with D7 | none |
| D19 | No session start while on Remote Control (corrected in batch 2: refused on turns another session started) | elsewhere | Claude desktop app, no home yet | raise upstream | none |
| D20 | SendMessage has no read receipt | elsewhere | Claude harness; workaround session-messages.md:27,87; PR #2990 | raise upstream | none |
| D21 | Item 19: ios-apps has no test-shape standard | new | new step ios-apps-test-shapes; extends decision test-practices P1 and P5 | to file | none |
| D22 | Item 20: the Pro lease blocks the Duo | owner + new | bin/sim-lease:185-186; owner ruling 2026-11-02 13:51 CST "The 18 Pro never runs beside a Duo"; stating the reason in sim-lease-tool.md needs no owner | ruled 21:59: no fixed sim limit, load brake only; step sim-lease-load-brake | none |
| D23 | Item 21: builder-test-edit blocks merges with test conflicts | ruled | step merge-conflict-mixed-roles (R31); a test-author owns a merge with test conflicts (builders-cannot-edit-tests.md:36-38, item 420 a) | in flight | none |
| D24 | Item 22: live hooks differ from the clone | new | new step live-hooks-diff-probe (lint/compliance_probes.py); skip hooks.SessionStart, which a cloud install rewrites; batch 3 adds: compliance-check names which copy it trusts | filed | none |
| D25 | Item 23: merge-forced restarts (evidence for D3; six restarts on Nov 12: 597 to 635 to 656; 605 to 667; 645; 674; 567) | ruled + new | decision pr-review-record:76,125,129 rules the fix check after a conflicted merge; the root cause is on main: merge/merge.py:25-28 takes a fix check only when a record was posted at the reviewed head; new step merge-tool-fix-check-no-earlier-log: accept a fix check that names the reviewed head and the fix diff | to file; rank asked of the owner | none |
| D26 | Item 24: Words probe counts false alarms | owner + new | new step words-probe-skips-kept-names (report only what the check would flag); a blanket slug skip departs from decision glossary-meets-owner-halfway | ruled 21:59: a, keep reading names | none |
| D27 | Correction: coordinator borrows idle lanes instead of queuing starts | ruled + new | borrowing lanes is ruled (session-tiers.md:143,179); new step refused-start-queues-turn; app half folds into D19 | to file | none |
| D28 | Item 25: builders read the one-build rule as Mac-wide | new | skill ios-apps "Sharing the Mac" opens with "Every session on this Mac shares its builds" and the bullet says it "widens ... to every session on the Mac"; new step one-build-per-session-wording: per-session scope first, and the builder brief says another session's build does not block yours | to file | none |
| D29 | Item 26: the iOS standard pins a runner with no iOS 27.1 SDK | new | skill ios-apps:22 pins `macos-26`; new step ios-runner-by-sdk: pin by the SDK the apps need, or name one exemption form; check runner cost first | to file | none |
