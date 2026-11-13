# Degen installs box-served first; the other apps install from the Mac first; TestFlight is the fallback

## The ruling

Owner, 2026-11-08 17:09 CST (Degen page item 157, pick b), confirmed 2026-11-09 03:35 CST (item 164, pick a): a Degen build reaches the phone by a box-served install first. TestFlight with auto-update is the fallback. The owner's note: "box-servered auto update / install into testflight with autoupdate as a back lane update". For Degen, it replaces the Mac-first install.

- The other apps: owner, 2026-10-22 19:40 CDT, for every app: when the phone is on Wi-Fi and the Mac can install, install from the Mac, with TestFlight as the fallback. That ruling stands for each app but Degen. Owner, 2026-11-09 19:31 CST (Degen item 171): box-first applies only to an app that has a box-served install path; today that is Degen alone. Every other app stays Mac first.
- The route that puts a CI build on the box is not built (Degen spec `cloud-move`, Phase 3). Until it exists, TestFlight carries each install from CI. `make phone` and `make testflight` stay on the Mac holdover until a CI build reaches the phone with no Mac (same spec, the Mac holdover table).
- The ship tool runs on the Mac today (decision `ios-ship-is-one-shared-tool`, one shared ship tool).
- When to install after a merge is not part of this ruling. It waits on the owner.

Why: the owner gave no reason. Beside it, Degen's work moves to cloud sessions, and the Mac keeps only a holdover (Degen spec `cloud-move`, a draft). For the Mac-first ruling: at 2026-10-22 08:11 CDT every TestFlight build on the team expired at once, for a cause still unknown; a Mac install does not depend on TestFlight. Unmeasured: TestFlight's delay to the phone, and whether iOS accepts the box's certificate for a box-served install.

Protected by the `ship path` item of `lint/compliance_probes.py ios`. It goes red when a repo's `phone` or `testflight` target does not call `ios-ship`. No check reads the box-served path yet.

Kind: process
Home: skills/ios-apps/SKILL.md
