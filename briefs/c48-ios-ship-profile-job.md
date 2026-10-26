# c48. ios-ship gets a profile job that waits until the phone is free

Written by the advisor, Oct 26. Owner agreed Oct 26 ("maybe at that time it needs more testing").
Rewritten Oct 26 against claude-settings main 3b96ce82 (c47 part 1, the account file, has landed). Owner's
word, Oct 26 (option b): no state wait; retry once after a fixed wait. Two parts: build (cloud), live check (Mac).

## Why

`xcrun xctrace record --device <UDID>` fails with "Waiting for device to boot" and then
"Timed out waiting for device to boot" (exit 13) on a network-paired iPhone. Live test, Oct 26
22:30-22:38 CDT (Xcode 27.1 27A9275, macOS 27.0, iOS 27.1, network transport):
- The developer disk image (DDI) was mounted and usable the whole time. It is not the cause, so
  `devicectl device info ddiServices` is not the fix.
- Recording 1 passed. Recording 2, about 17 s after recording 1 ended, failed. devicectl then
  showed the phone as `connected`, not `available (paired)`.
- 5 min later the phone was `available (paired)` again, and recording 3 passed.
Known elsewhere: developer.apple.com/forums/thread/694698 (since Xcode 13);
github.com/seedds/nxnative/issues/142 (iOS 27). The failure comes before the app launches, so it
holds for every app, not one repo.

## What part 0 found (Oct 26, Mac, phone unlocked)

The first recording failed "Timed out waiting for device to boot" (exit 13) while devicectl showed
`available (paired)` before and after, with no recording in the 35 min before. So the device state is
not a ready signal, and the cause is not only "busy after a recording". The wait-for-available design is
withdrawn.

## Part 1, claude-settings: `ios-ship profile`

1. New job: `ios-ship profile [CONFIG] --app NAME [--template T] [--time-limit S] [--output P]
   [--retry-wait S]`. Defaults: `Time Profiler`, 20 s, a printed path under `$TMPDIR`, retry wait
   60 s. Bundle id and UDID come from the config and account file as for `install`. One app per run.
2. Record by UDID, never by name: `xctrace record --template T --device <UDID> --time-limit S
   --output P --launch -- <bundle id>`, through the existing `step` timeout. No devicectl state poll.
3. If the output holds "Waiting for device to boot": print one line naming the wait, sleep the retry
   wait, and retry once. A second failure exits with xctrace's code, the log path, and one line saying
   the phone may need unlocking or a cable.
4. Header comment, usage line, README "Shipping iOS apps" and decision ios-ship-is-one-shared-tool:
   rewrite in place to name the third job and why it retries.

Proof, test-author first, red on main, in lint/test_ios_ship.sh (the `shell-macos` job), with
stubbed `xcrun` and a stubbed sleep:
- first xctrace passes: one call, exit 0, no sleep.
- first prints "Waiting for device to boot", second passes: two calls, one sleep of the retry wait, exit 0.
- both fail: two calls, xctrace's exit code.
- a failure without that text: one call, no retry, xctrace's code.
- the xctrace call carries the UDID, never a device name; `--retry-wait 5` changes the sleep.

Program logic: a fresh reviewer reads the diff (roles-solo-reviews-logic-diffs-only).

## Part 2, live check (on the Mac, phone unlocked)

`ios-ship profile --app <one app>` twice in a row. Record per run: passed first try, passed on retry,
or failed twice. If both runs fail twice, report it: the retry does not help, and the owner decides
whether to park c48.

Not in scope: a hook on `xctrace`, a CLAUDE.md line, ddiServices, a cable requirement.

Report cap: 15 lines per part.
