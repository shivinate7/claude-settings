# Prompt: close the gaps in bin/sim-lease and bin/sim-test

You are a claude-settings session. Close the gaps below in the phone simulator tools on main. These are `bin/sim-lease` (decision `sim-lease-tool`, the one simulator queue) and `bin/sim-test` (decision `sim-test-is-the-one-boot-path`). Read `docs/plans/sim-standard.md` on this branch for the owner's rulings, then plan the lanes yourself. The Mac sim gatekeeper session ("iPhone simulator gatekeeper takeover", local id 08a7ec88) found these gaps between 2026-11-06 and 2026-11-07 while it handed out phones to the Home, Degen, Apartment and mailaudit repos. Until they are fixed, that session hands out each Duo run by chat.

## Gaps, worst first

1. **A reuse takes no lease (ruling 4 of `sim-lease-tool`).** When `sim-test` reuses a booted Duo, `sim-lease status` shows no holder. So no session can see who is using the phone.
   - Incident, 2026-11-07 from 11:55 CST: Degen ran a test (sim-test pid 32870) and then a 900 s hold (pid 37130) on Duo 1. At the same time, the Home light tile design review (lane `home-lane-app-feel-core`, PR 547) drove Duo 1: it folded it, switched it to dark and tapped twice. Both results are suspect, and the review has lost 7 tries.
   - Fix to weigh: a reuse takes or renews a lease too, so `status` always names the user of a booted phone.
2. **Two runs held Duo 1 at once, in spite of the one Mac lock.** At 12:05 CST the lock's pid file named 32870, while hold pid 37130 had run for 7 min 06 s. The default lock wait is 300 s, so 37130 should have exited. Cause unread: maybe a raised `SIM_TEST_LOCK_WAIT`, or a race in the take-over. Find it with a test that goes red first.
3. **A stopped run skips its reset.** On 2026-11-07, Degen's h3-pill re-check of PR 449 (12:05 to 12:09 CST) was stopped mid-run. Duo 1 was left in Dark appearance (it was Light), with the Degen app maybe still installed. Nothing puts back the appearance, the fold or the installed app when a run ends early or a new holder takes over.
   - Fix to weigh: the next grant (or `give`) resets the appearance to Light and the fold to a known posture, and records what it changed.
4. **The 1-minute load bar of 60 lets crashes through.** Per the Degen coordinator (2026-11-06), three Duo crashes came at 1-minute loads of 58 to 71, on 2026-11-05 between 21:00 and 21:25 CST. Unmeasured here: no SpringBoard or PosterBoard report from 11-05 to 11-07 is in `~/Library/Logs/DiagnosticReports`. Measure it first, then set the bar.
5. **Slot 2 is never used.** `sim-test` holds one lock per Mac, so only one run goes at a time, and the two-Duo ruling (owner, 2026-11-02 14:23 and 14:47 CST) can never apply. Since 2026-11-06 13:31 CST, Degen runs on slot 1 only (owner ruling, Degen waiting page item 120 b). Duo 2 (801F55F4) has been shut down since a crash, with its theme and fold unchecked. Ask the owner whether slot 2 stays, before you change it.
6. **No priority and no silent-holder limit for a test run.** The queue is first in, first out, but the owner's goal (2026-11-02 13:00 CST) is "who is blocking more". A hold stops at 900 s, but a test run holding the lock has no time limit while its pid lives.
7. **A lane with no coordinator.** At 12:09 CST on 2026-11-07, the Degen lane `ios-ship-account` (sim-test pid 79492) took Duo 1. Its session is not on the session list, so no message could reach it. The tools must hold the line without relying on chat.

## Already measured (do not redo blind)

- Since PR 1202 (`sim-lease`) and PR 1246 (Duo by default, `--hold`) merged on 2026-11-04, `state/sim-boots.jsonl` shows 31 Duo 1 boots and 2 18 Pro boots from 11-05 19:53 to 11-06 13:38 CST. Over 11-04 to 11-06, guard.log shows no `simulator-boot-bypass` refusal.
- The reuse path holds the sim-test lock (header of `bin/sim-test`, lines 15 to 21). Only the lease is skipped.

## What I want

1. A test for each of gaps 1 to 3 that goes red on main first, then the fix.
2. `sim-lease status` names whoever is using each booted phone, reuse included.
3. Gaps 4 to 7: one record each, with the measure, or a question to the owner where the fix departs from a ruling.

Ask the owner before any erase of a shared device, and before any change to a runtime or to Xcode. Open no PR from this branch. Start your own lane from main.
