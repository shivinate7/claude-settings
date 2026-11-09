# A box-served install comes first, and TestFlight auto-update is the fallback

## The ruling

Owner, 2026-11-08 17:09 CST (Degen page item 157, pick b), confirmed 2026-11-09 03:35 CST (item 164, pick a): a build reaches the phone by a box-served install first. TestFlight with auto-update is the fallback. The owner's note: "box-servered auto update / install into testflight with autoupdate as a back lane update". For Degen, it replaces the Mac-first install.

- The owner gave it on Degen's page, during the move of Degen's work to cloud sessions. Whether it covers the other apps is open: asked through the Degen coordinator, 2026-11-09 03:45 CST.
- The route that puts a CI build on the box is not built (Degen spec `cloud-move`, Phase 3). Until it exists, TestFlight carries each install. `make phone` and `make testflight` stay on the Mac holdover until a CI build reaches the phone with no Mac (same spec, the Mac holdover table).
- The ship tool runs on the Mac today (decision `ios-ship-is-one-shared-tool`, one shared ship tool).
- When to install after a merge is not part of this ruling. It waits on the owner.

Why: Degen's work moved to cloud sessions, and the Mac keeps only a holdover (Degen spec `cloud-move`). Unmeasured: TestFlight's delay to the phone, and whether iOS accepts the box's certificate for a box-served install.

Protected by the `ship path` item of `lint/compliance_probes.py ios`. It goes red when a repo's `phone` or `testflight` target does not call `ios-ship`. No check reads the box-served path yet.

Kind: process
Home: skills/ios-apps/SKILL.md
