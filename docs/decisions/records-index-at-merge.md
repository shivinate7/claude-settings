# One records index page, rebuilt by the merge tool before ready

## Ruling

Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and
debt with a one-line gist. Only the merge tool rebuilds the page. A branch never edits the page by hand.

The tool rebuilds the page on the integration branch before the branch goes ready. `merge <pr> --confirm`
on a draft PR is that step, and it never merges. It refuses a head that does not hold the base tip, as
`--confirm` does, and a head that carries a claim. It commits the page alone, pushes it, and stops: mark
the PR ready, then run `--confirm` again. The tool sends no GraphQL, so the batch runner marks the PR ready
by its session's route (route pr-ready-mcp-cloud), after the draft run of the pushed head shows (skill
ci-hygiene). So the branch is final at ready, and the ready run is the merge run. The step claims no
record numbers. It takes no merge lock. A PR that turns draft after the first read is the one case: the step runs
under the lock that confirm already took, and releases it.
The same two allow rules cover both steps, so no new rule is needed.

Take a ready PR on the default branch with no record number to claim or resume. When its rebuilt page would
change the tree, `--confirm` refuses before any wait, claim or push. The refusal and the preview name
the remedy: return the PR to draft (route pr-draft-mcp-cloud), run
`merge <n> --confirm` on the draft, then mark it ready after its draft run shows. A head that holds a
Record-claim on a base with no stamp kinds first reverts that claim commit, since the draft step refuses a
claim head. A current page makes no
commit. A claim stays at confirm under the lock, so its numbers are free on the base tip, as before. The
claim commit carries the rebuilt page, so the claim and the page share one commit. That batch still runs
CI twice (unmeasured in other repos; none in this repo, Oct 24 to 31). The draft step refuses a claim head,
so the claim cannot move earlier. A resumed claim with a stale page still pushes the page, for the same
reason. When only the page conflicts with the base, the tool rebuilds it on the merged tree. That heal is
unchanged. Owner ask to stop the double CI run: Oct 31 14:12 CDT, repeated Nov 1 20:51 CST.

A lane never commits a change to `docs/records.md`, not even one made by `lint/hook_catalog.py`. PR CI
already accepts a stale page (`lint/hook_catalog.py --check` waives it on a PR run). The guard `records-page`
refuses a lane commit whose staged `docs/records.md` differs from the page on the lane's base. A merge of
the base into the lane brings the base's page, so it is allowed. While a merge is in progress, a commit whose page equals the page at MERGE_HEAD is allowed too, so a stacked lane can merge its base PR. The guard needs no exception for the tool:
it judges Claude's own Bash commands, and the tool's commit runs inside the tool.
The guard runs before the generator, so it cannot tell whether a chained `generator && git add && git commit`
will change the page. It refuses such a chain even when the page ends unchanged. The refusal is exact for what
it can see.
Cost of the guard: eight git processes per judged `git commit`, that is, each commit with no paths, or with a path that names the page. One finds the top, two find the base, three read the HEAD, base and origin pages, one opens the base page, and one reads the commit's page. `-a` adds one `ls-files`, and each `git add` in the command adds one top read. One more read, of MERGE_HEAD's page, runs only when the page differs from all three. No test pins this count. A failed MERGE_HEAD read leaves the refusal; a failed HEAD or base read lets the commit through. The allowance takes the page of any branch being merged in, not only the PR's base. A hook makes no network read to learn the base, and the merge tool rebuilds the page at merge.

The heal stops when the generator writes no page for a conflicted page. The merge runs only the records
mode of the generator (`--records-only`). A broken generator import prints one line. The heal-wait stop
paths have tests. `RECORDS_HEADER` in `hooks/guard_merge.py` copies the first line of `RECORDS_INTRO` in
`lint/hook_catalog.py`, and a pin test compares them.

Reason: a hand-kept index goes stale at the first merge that forgets it, so the tool owns it. Lanes that
each rebuilt the page conflicted on it in three batches. A rebuild at confirm came after the ready run: 15
of 50 merges to main, Oct 24 to 31, ended on that commit and ran CI twice. None ended on a claim commit.

Kind: build
Plan: docs/decisions/records-index-at-merge.md#ruling (all)
Home: lint/hook_catalog.py
