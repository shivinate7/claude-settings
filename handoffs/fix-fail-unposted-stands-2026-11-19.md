# Handoff: lane fix-fail-unposted-stands (2026-11-19)

Repo: shivinate7/claude-settings. Session: session_013NEJL1... (this lane, cloud). Coordinator: session_013NEJL1gw6EdrSyvHkTUEx6.

## Branches and PRs

- PR 3515, draft. Branch `fix-fail-unposted-stands`, head `1ca59cda9d35d0105be55fb88000ebed766054a8`. Docs-only edit of decision `pr-review-record`. Reviewer round 1 PASS (reviewer haiku). Lane lint PASS at this head with PR_BODY set to the PR body (the bare run failed `aligned` as unknown). Main merged in: already up to date at 2026-11-15.
- PR 3693, draft. Branch `allow-lane-lint-perm`, head `5c61595fbe275a5b91ce39694eae4043fb1f5f36`. Adds `Bash(python3 merge/merge.py --lane-lint:*)` to `permissions.allow` in root `settings.json`. Guard path, so Guard or check is `yes`. No review record yet.

## Done

- The sentence in the bullet "One fix verifier per record" says: an unposted FAIL fix check counts for nothing, the posted PASS stands and ends review, a posted FAIL still sends the fix to the fresh full review. Cites owner item 866 a, 2026-11-15 11:34 CST. Posted FAIL then PASS at a later head is not covered, and the line-139 refusal is not widened.
- Proof that no code changes: `review_records` in `merge/merge.py` feeds `earlier` in the `--review-record` handler, so the tool reads posted lines only.
- Inbox item `fb-1145-1` filed. Message sent to triage session_013NEJKzyLYRTQKeLpis8JKJ about the cloud problems below.

## Unfinished

- Owner pick open: apply the reviewer's wording notes to PR 3515 (end review at its Head, name `review_comments`, note the design-reviewer hold on line 72), or keep as is. Recommended: keep.
- Reviewer round 1 on PR 3693.
- Batch runner marks PR 3515 ready. This lane never does.
- Roadmap ruling `own-833-a-done-at-fix-check` marks the failed-then-fixed case "unmeasured". It lives on the roadmap branch, which only triage writes. Not edited.

## Next step

Owner answers the wording pick. Then a fix verifier if the head moves, else the batch runner takes PR 3515.

## Refused acts

- `merge --lane-lint` bare: refused by guards `check-tail` and `check-timeout` (want `verdict`, not installed in cloud). `override 1h` lifted neither. Run in the background with a 3900000 ms limit instead.
- Guards `hand-made-worktree`, `silent-write` (`git push -q`) and `detached-launch` each refused one command.
- The lane lint's own refusal says no override lifts it.

## Owner rulings held

- Item 866 a (2026-11-15 11:34 CST): the posted fix-check PASS stands.
- `override 1h` and "change settings json for the repo to add an allow permission" (2026-11-15 12:10 CST): produced PR 3693.
- "open and also message triage" (2026-11-19): opened PR 3693, messaged triage.

## Agents

- Reviewer round 1 on PR 3515 (haiku): finished, PASS. Worked in its own worktree on branch `fix-fail-unposted-stands`. None running.
