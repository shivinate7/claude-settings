# Every iOS app installs from the Mac first, and TestFlight is the fallback

## The ruling

Owner, 2026-10-22 19:40 CDT, for every app: when the phone is on Wi-Fi and the Mac can install, install from the Mac. TestFlight is the fallback. In each repo, `make phone` runs `ios-ship install`. When it fails, `make testflight` runs `ios-ship testflight` on the same commit.

- The ruling amends the owner's ruling of 2026-10-21 13:58 CDT, which shipped through TestFlight only.
- Before this record, the ruling lived only in mailaudit (its decision `native-ships-via-testflight`). This record is its home for every app. The `ios-apps` skill states it as part of the iOS standard.
- When to install after a merge is not part of this ruling. It waits on the owner.

Why: the owner's record of the ruling gives no reason. One fact sits beside it in mailaudit's record: at 2026-10-22 08:11 CDT every TestFlight build on the team expired at once, for a cause still unknown. A Mac install does not depend on TestFlight. TestFlight still reaches the phone when it is away from the Mac.

Protected by the `ship path` item of `lint/compliance_probes.py ios`. It goes red when a repo's `phone` or `testflight` target does not call `ios-ship`.

Kind: process
Home: skills/ios-apps/SKILL.md
