# A ready mark warns when the session has not subscribed

## The ruling

Owner, 2026-11-13 21:39 CST, in a batch runner's chat (relayed by the runner and the consultant): "why are u not setting a watcher and or just polling to be woken? why setting check ins". A session that waits on CI calls `subscribe_pr_activity` for the PR first. It keeps one long check-in as a safety net (rule `git-ci-wait-checks-in`).

- `hooks/ready_subscribe_warn.py` is a PreToolUse hook on `mcp__github__update_pull_request`. It acts only on a call with `draft` false, the cloud's ready route. `ci_wake.mcp_ready_calls` parses that call, the one parser of it.
- It reads the session's transcript once, through `lint/_transcript.py`. The last counted `subscribe_pr_activity` or `unsubscribe_pr_activity` call for that owner, repo and PR number decides. A subscribe counts unless its result is an error (`is_error`, or a failed `toolUseResult`) or its text says "already watching", in any case, in a plain string or a content-list block. The subscribe tool's own description says a call for a PR another Claude agent already watches succeeds but delivers no events to this session. The exact result wording is unmeasured. The hook matches "already watching" case-insensitively. A different real wording fails open: a missed warning, never a false one. A subscribe with no result record counts, so the hook fails open. A counted subscribe as the last word is silence. An unsubscribe, or none, prints one `additionalContext` warning that names `subscribe_pr_activity`.
- It never sets a permissionDecision, so it never refuses the ready mark. Whether the model receives a PreToolUse `additionalContext` is unmeasured (step `ci-wait-warning-cry-wolf-count`): no other PreToolUse hook in this repo emits one. It fails open and silent on bad input, a missing transcript or any error.
- A call in a sidechain record counts. A subscribe that sits only in a resumed `api-request-blob` copy does not, because the shared reader yields no call from one. `hooks/test_ready_subscribe_warn.py` pins both (the blob case is the owner lane's ruling).

Owner, 2026-11-13 22:24 CST (page item 804, option a; relayed by triage and the coordinator): ship pull request #3346 now and measure after. Ruling `own-cry-wolf-gate-waived` waives the pre-ship cry-wolf count for that pull request only. Still owed under step `ci-wait-warning-cry-wolf-count`: the cry-wolf count and the reach test. <!-- glossary-ok: the ruling's id as filed; renaming it would break the cite -->

## The mistake and the harm

A batch runner (runner 10) set timed check-ins on PR 3302 and no subscription. Its run ended at 21:33 CST, and a rerun came at about 21:37 CST (the consultant's account, unchecked). The harm: a late rerun on the top-priority PR. A subscription wakes the session on CI results, a comment, and a review. A red run posts a `ci-done` comment, which the subscription also delivers (decision `ci-wait-reads-run-status`).

## Why warn, not refuse

A ready mark with no subscription is not always wrong. A session may mark ready and merge with no wait, because the checks already passed or the owner asked for it. How often that happens is unmeasured (step `ci-wait-warning-cry-wolf-count`). A refusal would stop those sessions, so the hook warns once per ready mark. It is a nudge, and the rule is still a rule.

## Limits

- A failed unsubscribe still cancels the subscribe in the hook's state, so the next ready mark can warn falsely. Warn-only and rare. A note, not a debt.
- The subscribe call's keys (owner, repo, pullNumber) match the tool's schema, read from the tool definition. Unmeasured on a live call.

## Cost

One transcript read per ready mark, with no other process, timer, file or log, pinned by `hooks/test_ready_subscribe_warn.py` (`case_ready_mark_reads_once_and_starts_nothing_else`). A call that is not a ready mark reads no transcript, and the silent cases of the same test prove that gate.
Kind: process
Home: hooks/ready_subscribe_warn.py
