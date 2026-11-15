---
id: pending
slug: gh-api-budget
---

# The GitHub API budget is read from each reply, and a bulk read stops below a tenth

## The ruling

Incident: at 12:05 CST on Nov 15, 2026 the REST core budget of the shared token read 15,000 of 15,000 spent. Every `gh` call of every session then failed until the hourly reset. No record named which tool spent it.

`merge/merge.py` is the one home of the repo's GitHub reads, through `Host.gh`, `Host.api` and `Host.pages`. It does five things there.

- **Measured limit.** The limit is 15,000 calls an hour for each token, read from `X-Ratelimit-Limit` in the replies at the incident. The tool reads the limit from each reply and never holds the number.
- **Budget from each reply.** `Host.api` passes `-i` on every call, and `Host.pages` already did. `Host.gh` keeps `X-Ratelimit-Remaining`, `-Limit` and `-Reset` from each reply that carries a header block (`Host.budget`). A reply with headers and no ratelimit headers resets all three to unknown, and an unknown budget never refuses. A reply with no header block (a transport error) leaves the last budget in place. No call is made to read the budget.
- **Read kinds.** A bulk read is a list read of the whole repo: `merge --reviewed`'s open pull request list and repo-wide comment read, `merge --audit-prs`, and any caller that passes `bulk=True` or runs inside `bulk_reads`. It is refused, with no call, when remaining is under a tenth of the limit. The refusal names remaining, limit and the reset time in Central time. A missing or unreadable header never refuses. A merge-path read (the pull request, its head's checks, the protection, the claim, the merge) and every write are never refused: a merge that is under way must finish.
- **The memo and its bypass.** A GET is kept for the run, keyed on its route and query. A repeat is no call. Any write through `Host.api` clears the memo. A bulk read is always sent and is never kept, so it reads fresh. A read that waits for something to change passes `memo=False`: `read_pr` (the poll of `wait_pushed_head`, which waits for the head to move after a push) and the two pull request reads around the merge call. A poll that read the memo would see the old head until its deadline. `protection_names` holds its answer in the same memo, a 404 included, so a run reads the ruleset and the branch protection once. `Host.runs` holds each head's `gh run list` in the same memo, so `superseded`, `head_state` and `run_state` read a head's run list once. A failed run list read is not kept. A merge under the lock (`confirm`) turns the memo off (`Host.use_memo`): it reads each state fresh, because a rate wait or a rival run can change it between two reads.
- **Attribution.** `Host` counts each `gh` call by method and route template (`pulls/{n}/files`), retries included. `merge --audit-prs` prints the counts.

`merge --reviewed` reads each head's check runs, statuses and workflow run list once: the lint step's `rollup_green` and the CI state (`head_state`) take the same reads through the memo. A head whose check rows link two runs reads its run list once too.

## Reader

`merge --audit-prs`: one bulk list of the open pull requests and one repo-wide `issues/comments` read. It prints one line for each pull request: number, branch, head, draft or ready, mergeable state, the newest review record's last round and verdict, and the lane-lint state. A record with a fix check and no round line shows the fix check's verdict, and one with neither shows `no round`. `-C <checkout>` names the checkout to audit; any other flag or a pull request number is refused. The pull request list does not carry the mergeable state, so it prints UNKNOWN. This is accepted: a read for each pull request is the cost the audit avoids. The last lines give the calls for each route. It writes no file.

## Cost

No new process. No file and no temp file. No extra call: the budget comes from the reply of a call already made, and the memo removes calls. `--audit-prs` costs a call for each page of the open pull request list and a call for each page of comments.

## Not built

- A hook that counts every `gh` call of every session (the loop hook). It would run on every tool call (rule `outcomes-mechanize-rules`). It waits for an incident that this tool's counts cannot answer.
- GraphQL. A cloud session refuses it (HTTP 403), and this tool sends none.
- A change to `hooks/ci_wake.py`. Its back-off is the owner's ruling (`ci-wait-reads-run-status`).

Tests: classes `GhApiBudget`, `AuditPrs`, `ReviewedList` and `RepoDirFlag` in `merge/test_merge.py`.

Kind: process
Home: merge/merge.py
