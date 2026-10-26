# c48. ios-ship gets a profile job that waits until the phone is free

Written by the advisor, Oct 26. Owner agreed Oct 26 ("maybe at that time it needs more testing").
Checked against claude-settings 149f4bc. Start after c47 part 1 merges (both edit bin/ios-ship).
Three parts, in this order: measure, build, record.

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

## Part 0, measure first (on the Mac, phone awake; no code change)

Unmeasured: how long the phone stays busy (17 s to 5 min), and whether the device state is a
reliable signal. Run 3 rounds by UDID: record 10 s; then poll `xcrun devicectl list devices`
every 10 s, and record the time the phone shows `available (paired)` again; record again at once.
Report per round: seconds until `available`, and whether the next recording passed. If a
recording fails while the phone shows `available`, stop and report: the wait signal is wrong and
part 1 needs a new design (ask the owner). Also try once with a cable, if one is at hand; say if not.

## Part 1, claude-settings: `ios-ship profile`

1. New job: `ios-ship profile [CONFIG] --app NAME [--template T] [--time-limit S] [--output P]`.
   Defaults: `Time Profiler`, 20 s, a printed path under `$TMPDIR`. Bundle id and UDID come from
   the config and account file as for `install` (c47). One app per run.
2. Before recording: poll `devicectl list devices` until the phone shows `available (paired)`.
   Cap: twice the longest wait part 0 measured, at least 60 s. Past the cap: exit 75 (the
   existing "phone not reachable" code) with one line naming the state seen.
3. Record by UDID, never by name: `xctrace record --template T --device <UDID> --time-limit S
   --output P --launch -- <bundle id>`, through the existing `step` timeout.
4. If the output holds "Waiting for device to boot": wait for `available` again (same cap) and
   retry once. A second failure exits with xctrace's code and the log path.
5. Header comment, usage line, README "Shipping iOS apps" and decision ios-ship-is-one-shared-tool:
   rewrite in place to name the third job and why it waits.

Proof, test-author first, red on main, in lint/test_ios_ship.sh (the `shell-macos` job), with
stubbed `xcrun`:
- phone `connected` then `available`: one xctrace call, after the state turns.
- phone never `available`: exit 75, no xctrace call.
- first xctrace prints "Waiting for device to boot", second passes: exactly two calls, exit 0.
- both fail: two calls, xctrace's exit code.
- the xctrace call carries the UDID, never a device name.

Program logic: a fresh reviewer reads the diff (roles-solo-reviews-logic-diffs-only).

## Part 2, live check (on the Mac)

`ios-ship profile --app <one app>` twice in a row, the second within 20 s of the first. Both
must pass; the second must show the wait in its log. Record the verdict and the wait.

Not in scope: a hook on `xctrace`, a CLAUDE.md line, ddiServices.

Report cap: 15 lines per part.
