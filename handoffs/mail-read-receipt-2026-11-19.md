# Handoff: lane mail-read-receipt (2026-11-19 00:30 CST)

Slug: mail-read-receipt. Step: mail-read-receipt (roadmap cb1d5bfee). Repo: shivinate7/claude-settings.
Session: session_013NEJL1H8rtZDDYaw58WXbw (lane). Coordinator: session_013NEJL1gw6EdrSyvHkTUEx6.

## Branch and PR

- Branch: `mail-read-receipt`, head 29c9b8462f95b76086a5f750fe1434262bfeea56 (6 commits on main 8d7d36bd9).
- PR #3137, open, draft, not merged. Live read 2026-11-19: mergeable_state `dirty` (main moved to a later tip; the PR base shows 7dd44c41c). The head was not rebased or merged with main.
- Hand-in: sent to the batch runner (session_013NEJL2f1YCYsvLdpFqtWP3) on 2026-11-13. No merge since. Never marked ready.

## What is done

- `mail status <id>` built: prints `open`, or `taken <time> by <taker>` (read from the Taken-by line); unknown id reads `unknown` (exit 1); an id with "/" or empty reads `bad address or id` (exit 2) before any git call; a git fault prints `mail unknown: <reason>`. Reads refs/heads/mail once (ls-remote, fetch, ls-tree, plus show when taken). Writes no message, ref or log.
- Files: hooks/mail.py (`message_status`, `TAKEN_BY`), bin/mail (`status`), hooks/test_mail.py (17 StatusCommand cases), docs/decisions/session-messages.md (status bullet with cost), skills/waiting-page/reference/routing-and-sessions.md line 51.
- Red first: 13 cases red on main (commit 3840d2aea), 3 more red on 040f5dffc (dec57eb33).
- Reviews: round 1 FAIL (haiku; slash id printed `open`); fix checks PASS (sonnet) at 9264dc8f3 and 29c9b8462; round 3 PASS (sonnet), net value zero. Review record posted at 29c9b8462 (Kind normal, Guard or check yes, rounds 1 FAIL, 2 PASS, 3 PASS, net zero). It has no Fix check line.
- `merge --lane-lint 3137` PASS at 29c9b8462 (third run; first two failed on the flaky test_no_shard_runs_all, triage-confirmed, fix is PR #3149).

## Unfinished

- Merge: not done. Needs the head brought up to date with main (batch runner's standing grant: plain merge of main into a handed-in branch; a clean merge of main takes no new review), then the lint and the merge tool.
- Three test-gap notes, sent to triage (session_013NEJKzCzoWhfP8FMCPtQU6) on 2026-11-13, not pushed: (1) no no-write or read-count assert in a StatusCommand case that runs on Windows (the four stand-in cases skip on nt; assert `store.tip()` unchanged in test_untaken_message_reads_open_exit_0); (2) surviving mutant: dropping the leading "/" in the name match in `message_status` makes a suffix id read open, all 17 pass; add a suffix id to test_unknown_id_reads_unknown_exit_1_and_never_open; (3) surviving mutant: `stamped[-1]` to `stamped[0]` passes all 17; add a done file with a quoted Taken-by line in its body ahead of the real stamp.
- `check_unknown_reads_contract` has no mail member, so it does not cover `status`.
- Tell retro (session_013NEJKz5AWFJhGvmCUoi6wQ) when it merges: not done, because it has not merged.

## Next step

Batch runner (or a successor lane): merge main into `mail-read-receipt`, re-run `merge --lane-lint 3137`, read the review state with `merge --reviewed`, then merge with the merge tool. Then tell retro.

## Refused acts and notes

- `git worktree add` by the test-author: refused by the hand-made-worktree guard (possible false alarm; the guard text seems to allow a red-run checkout).
- `SendMessage` to a `session_` id: refused (route is the remote send_message tool).
- A build-agent spawn without a model and a reviewer spawn with `model sonnet` for round 1 were refused by agent-model-cap; both fixed by the remedy printed. No override typed.
- Builder pushed the round-2 fix before a record existed at 040f5dffc, so the record chain has no Fix check line.

## Owner rulings I hold

- Owner 09:06 CST Nov 13 (relayed by retro): D20, no read receipt: build it in our own mailbox. Home: step mail-read-receipt (roadmap) and decision session-messages (status bullet, in the PR).
- Lane draft PR grant (owner, 2026-11-12 17:19 CST): used once, to open PR #3137.

## Agents (all finished, none running)

- test-author, haiku: id a6c8af20843d72e7e. Worktree .claude/worktrees/agent-a6c8af20843d72e7e. Branches: mail-read-receipt-red (3840d2aea), mail-read-receipt-red2 (dec57eb33), mail-read-receipt-red3 (a65423813), all pushed.
- builder, sonnet: id aefe8639a6fd780ba. Worktree .claude/worktrees/agent-aefe8639a6fd780ba. Branch mail-read-receipt (040f5dffc, 9264dc8f3, 29c9b8462), pushed.
- reviewer round 1, haiku: id ac9f165ffc14a7769. Fix verifiers, sonnet: a765f01184c7efcd4, ae5f1c5a5ba2435e7. Round 3, sonnet: a89674cc3a7742de5. Each in its own worktree under .claude/worktrees/agent-<id>; none edits.
