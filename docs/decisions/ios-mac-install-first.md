# A box-served install comes first, and TestFlight auto-update is the fallback

## The ruling

Owner, 2026-11-08 17:09 CST (Degen page item 157, pick b), confirmed 2026-11-09 03:35 CST (item 164, pick a): a build reaches the phone by a box-served install first. TestFlight with auto-update is the fallback. The owner's note: "box-servered auto update / install into testflight with autoupdate as a back lane update". It replaces the Mac-first install.

- The owner gave it on Degen's page, during the move of Degen's work to cloud sessions. Whether it also covers the other apps is not stated. Until the owner says, an app whose sessions still run on the Mac installs from the Mac first.
- The route that puts a CI build on the box is not built (Degen spec `cloud-move`, Phase 0). Until it exists, TestFlight carries each install.
- When to install after a merge is not part of this ruling. It waits on the owner.

Why: Degen's work moved to cloud sessions, so no session runs on the Mac to install from it (Degen spec `cloud-move`). TestFlight still reaches the phone anywhere. Unmeasured: whether iOS accepts the box's certificate for a box-served install.

Protected by the `ship path` item of `lint/compliance_probes.py ios`. It goes red when a repo's `phone` or `testflight` target does not call `ios-ship`. No check reads the box-served path yet.

Kind: process
Home: skills/ios-apps/SKILL.md
