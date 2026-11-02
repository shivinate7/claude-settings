# iPhone and Mac app tests run in full at milestones

## The ruling

Owner, 2026-11-02 (waiting page item 133, pick a), roadmap step tci-5-platform-tested: a batch of an iPhone or Mac app merges on quick checks. After a set number of app batches, or at a milestone the owner names, one full Swift run on a GitHub Mac machine tests main. A red run blocks the next merge until it is fixed.

- Basis: the owner's Oct 27 CI ruling (`ci-cut-in-steps`, step 3, milestone runs).
- Not a full Swift run on every app batch (option b). It costs the most Mac minutes, about 10 times the cost of Linux minutes, on every batch.
- Not a repo exemption that keeps its own Mac run (option c). Not picked.

Cost: the Mac runs only at milestones. A broken batch can sit on main until the next milestone run finds it.

Kind: process
Home: skills/ios-apps/SKILL.md
