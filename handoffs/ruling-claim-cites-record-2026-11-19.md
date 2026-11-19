# Handoff: lane ruling-claim-cites-record, 2026-11-19 00:26 CST

Written for the coordinator's wind-down order (relayed, 00:24 CST). Session c85e6059-6b01-5b75-92f7-b8c458445af7. Repo shivinate7/claude-settings.

## Slug and branch
- Slug: ruling-claim-cites-record (roadmap step of the same name).
- Branch on origin: `ruling-claim-cites-record`. Head: `f1e3255a44758c2a9f687c3247bd25f5508029db` (read live 00:25 CST).

## Open PR
- #3330, draft, open, mergeable_state clean at 00:25 CST. Head as above. Base is #3206's branch `rebuild/past-ruling-on-send` (head 30b41d600836ee06fd8c94baaf3938e2ac35343e), not main.
- Not marked ready. Not merged. #3206 is still open, and a re-stack of #3330 onto main after it merges is a new head and needs a fix check chained to the review record below.

## Done
- New check `lint/check_ruling_claims.py`: refuses a brief, test comment or code comment that names an owner ruling (a dated time claim, or `ruling <id>`) with no record behind it. Incident form `owner ruling 14:19 CST` exits 1. Named escape `no record: <reason>`.
- `lint/test_check_ruling_claims.py` (19 methods, red cases first: 25, 41, 20 red on the three earlier heads).
- CI: fixture suite and PR check steps in `.github/workflows/checks.yml`.
- Two notes in `docs/debts/notes.md`: ruling-claims-brief-unwired, ruling-claims-dated-line-backs.
- Lane lint: `merge --lane-lint 3330` PASS at the live head (21:25 CST Nov 13).
- Review record posted and read back at the live head: https://github.com/shivinate7/claude-settings/pull/3330#issuecomment-6871052831 . `merge --reviewed` read: `#3330 ruling-claim-cites-record f1e3255a4 done: round 1 passed; CI draft, no run`.
- Hand-in sent to runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) at 21:34 CST Nov 13.

## Unfinished
- PR still draft, waiting behind #3206 (the coordinator said #3206 conflicts with #3314's tree and waits behind it).
- Three non-blocking round 1 limits are not filed as notes: a lowercase `owner ruling` plus a hyphenated word in prose reads as an id claim; the usual cite style with an item number (for example "Owner ruling 745 b (page item 745...), <date> <time>") is not read; a PR that moves an old fixture block re-adds an old claim and is refused. Runner 10 was told; the coordinator said the two filed notes stay with this lane and triage was told.
- `docs/debts/scan-quote-led-password-host.md` line 5 holds an old claim with no record. Base mode never reads old lines.

## Next step
After #3206 merges: re-stack #3330 onto main (new head), run a fix check chained to the review record, run `merge --lane-lint` once on the new head, hand in to the batch runner. Do not mark ready.

## Refused or blocked acts
- `merge --review-record --fix-check` refused for the old heads (it needs an earlier posted record at the reviewed head). The coordinator picked a fresh round 1 at the live head instead. No override used.
- Hook-refused spawns: a sonnet model on the test-author spawn; a spawn naming no model. Both fixed by naming the role's model.
- `verdict` is not installed in this cloud sandbox; checks ran directly.

## Owner rulings held
- None of my own. Coordinator pick 21:26 CST Nov 13 (relayed, undoable): no hand-written record; one fresh round 1 at the live head. The R9 reading (a passing round ends review) has its home in #3269, not on main when I read it.
- The grant words in the start message were the coordinator's; I filed them as not-a-grant in the inbox file for this session.

## Agents (name, role, model, branch), all stopped
- ta-ruling-claims: test-author, haiku (role default). Branches ta3-claims, ta4-claims, worktree-agent-af93c85473d433251. My earlier reports said sonnet; that was wrong.
- b-ruling-claims: builder, sonnet. Branch b2-claims, worktree-agent-aaa8122e9be789168.
- b3-ruling-claims: builder, opus (round 3). Branches b3-claims, b3-narration.
- b4-nowindow-fix: builder, sonnet. Branch nowindow-fix (commit f1e3255a4, now the PR head).
- r1, r2, r3, fv, fv2, r1b-ruling-claims: reviewers, sonnet. Review order: r1 FAIL, r2 FAIL, r3 FAIL (CI only), fv PASS, fv2 PASS, r1b round 1 PASS at the live head.
- Their worktrees are gone or unneeded; every commit that matters is on the PR branch.
