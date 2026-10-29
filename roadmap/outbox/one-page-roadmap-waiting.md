# c136, one page per repo

- Draft PR #810, branch `c136-one-page`, head 5e362f89, with origin/main 0f6a1487 merged in.
- Review round 3 passed. The design review of the built page, round 3 (the cap), passes every view but one: at 372 to 380 px the rail splits a phase name. It is now the debt `docs/debts/rail-375-splits-phase-name.md`.
- Gates on the head pass: page.test.mjs, roadmap test_build, waiting-page unittests, ste-changed, check_silent_undo --strict, ci-job checks --lint.
- Open: the once-per-batch live republish check. Queued follow-up lanes for after #810 merges: the 375 rail fix, and the old two-page wording in `skills/project-ops/SKILL.md` and `GLOSSARY.md`.
- Resume: read PR #810. The contract is the Build constraints section of `docs/design/one-page-notes.md`.
