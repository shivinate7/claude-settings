# c159-main-ref-install (cloud lane, Oct 28)

- c159: green and reviewed. Draft PR 733 (main-ref installer fix), branch `c159-main-ref-install`, head 833a594, from main e0f9e2d. Builder Opus; reviewer round 1 Opus (NOT CLEAR: silent success outside a repo, fixed in 833a594), round 2 Sonnet (CLEAR).
- c159: the 6 new cases were red, then green. `verdict ste-changed main` PASS. shellcheck is not installed and did not run.
- New finding, needs its own lane: the `test_hook.sh` case "fetch origin main:main, origin/main stale" is red on untouched main e0f9e2d with git 2.43. The hook refuses: "<sha> is not on origin/main". The cause is in the reference-transaction hook logic. Guess, unmeasured: a non-atomic fetch updates each ref in its own transaction. gates.yml line 420 runs this suite in CI; I have not checked whether CI's git version passes it.
- Notes kept from review, not debts: (1) a per-worktree hooksPath (worktreeConfig) is read only for the current worktree; (2) a tracked hooks dir shows the copies as untracked; (3) an existing different hook is overwritten, as on main; (4) when the `.git`-is-a-file ERROR fires, it stops the worktree loop.
- Container: the round-1 reviewer's probe left /hooks/reference-transaction (a 55-byte test hook, not the guard). The safety check refused my removal; it stays in this ephemeral container.
- Deviation: the brief named an Opus reviewer. Round 2 ran Sonnet, per `roles-third-try-steps-up` (reviewers run Sonnet from round 2 on).
