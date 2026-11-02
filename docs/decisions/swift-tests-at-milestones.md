# iPhone and Mac app tests run in full at milestones

## The ruling

Owner, 2026-10-27 12:07 CDT, roadmap step c95 (decision `ci-cut-in-steps`, step 3, milestone runs): full-scale test runs happen at milestones, not on every merge. It applies to iPhone and Mac app tests from 2026-11-01 18:44 CST (roadmap step tci-5-platform-tested). A batch of an app merges on quick checks. A full Swift run on a GitHub Mac machine tests main at a milestone.

- Incident: waiting page item 133 asked this again. The owner answered "none" at 2026-11-01 18:38 CST ("I thought we agreed most full-scale tests are done at a milestone level"), and triage closed it as already ruled.
- The cadence of milestone runs (a count of app batches, or a milestone the owner names) is not ruled yet.

Cost: the Mac runs only at milestones. A broken batch can sit on main until the next milestone run finds it.

Kind: process
Home: skills/ios-apps/SKILL.md
