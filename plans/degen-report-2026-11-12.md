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

## Ledger

Classes: ruled (already ruled or fixed), step (an existing step takes it), new (a new step), owner (needs the owner's call), elsewhere (not claude-settings).

| # | Finding | Class | Home | Status | Proof |
|---|---|---|---|---|---|
| D1 | Inbox hook misses page read-backs | step | step artifact-guard-matcher-names, PRs #2923-#2927 | in flight | none |
| D2 | Local page republish has no pictures | step + new | step artifact-guard-matcher-names; rest: new step local-page-publish-route | partly in flight | none |
| D3 | No fix-check exception for merge-forced tests | owner | pr-review-record.md:76-77, merge.py:5561-5568 | asked | none |
| D4 | No guard on box writes in read-only audits | new | new step readonly-agent-shell-write | filed, roadmap 378ff3a35 | none |
| D5 | No check before a "not worse than main" claim | new | new step claim-vs-main-needs-read, extends #2765 | filed, roadmap 378ff3a35 | none |
| D6 | CI waits have no enforcer | step + new | wake: step red-job-wakes-runner (#2860); stop: new step ci-wait-stop-needs-checkin | partly in flight | none |
| D7 | Role-model guard ignores its own override | owner | with D18: guard.py:3836-3849, call_judge.py:32,324-343; step role-model-explore-veto-offer once ruled | asked | none |
| D8 | Haiku round-1 reviews against Sonnet records | step | step model-table-one-home (#3010), step round1-sonnet-guard-table | in flight | none |
| D9 | builder-test-edit refuses comment-only edits | owner | decision builders-cannot-edit-tests, ruling 437 a; step builder-test-comment-edit once ruled | asked | none |
| D10 | Live pin fell 439 commits behind | new | new step session-start-pin-skip-log | filed, roadmap 378ff3a35 | none |
| D11 | Simulator noise list has no shared home | new | new step sim-boot-noise-off (bin/sim-test), one lane with D12 | filed, roadmap 378ff3a35 | none |
| D12 | Simulator wallpaper store grows without limit | new | new step sim-wallpaper-store-drop (bin/sim-test), one lane with D11 | filed, roadmap 378ff3a35 | none |
| D13 | Pin the Duo to the 27.2 runtime | owner | skill ios-apps device IDs; step sim-lease-gaps asks the owner first | asked | none |
| D14 | Session checkouts go stale | new + owner | (b) new step guards-read-origin-main-config (git_reads.py:305, question_form.py:1062-1077); (a) owner, reverses step grants-read-from-main | asked | none |
| D15 | No trusted relay of an owner chat grant | step | step page-wakes-and-relays, PR #3038 | in flight | none |
| D16 | Isolation check refuses edits outside git | elsewhere | Claude Code harness; step harness-worktree-git-probe; debt note split-sentence-eight-copies | raise upstream | none |
| D17 | Inbox needs an item for every message | owner | decision owner-feedback-inbox, feedback_guard.py:241-248; step inbox-skip-bash-echo once ruled | asked | none |
| D18 | Model-cap guards disagree | owner | same root as D7 | asked | none |
| D19 | No session start while on Remote Control | elsewhere | Claude desktop app, no home yet | raise upstream | none |
| D20 | SendMessage has no read receipt | elsewhere | Claude harness; workaround session-messages.md:27,87; PR #2990 | raise upstream | none |
