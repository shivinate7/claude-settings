# One records index page, rebuilt by the merge tool before ready

## Ruling

Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and
debt with a one-line gist. Only the merge tool rebuilds the page. A branch never edits the page by hand.

The tool rebuilds the page on the integration branch before the branch goes ready. `merge <pr> --confirm`
on a draft PR is that step, and it never merges. It refuses a head that does not hold the base tip, as
`--confirm` does, and a head that carries a claim. It commits the page alone, pushes it, and stops: mark
the PR ready, then run `--confirm` again. The tool sends no GraphQL (a cloud session's `gh` gets 403 on
it), so the batch runner marks the PR ready, after the draft run of the pushed head shows (skill
ci-hygiene). So the branch is final at ready, and the ready run is the merge run. The step claims no
record numbers. It takes no merge lock, except when a PR turns draft after the first read: then it runs
under the lock that confirm already took, and releases it.
The same two allow rules cover both steps, so no new rule is needed.

`--confirm` on a ready PR rebuilds the page and claims record numbers under the merge lock. A page that is
current makes no commit. A stale page (no draft step, or the base gained a record since) gets the rebuild commit, and
that commit needs a second CI run. A claim stays at confirm, so its numbers are free on the base tip under
the lock, as before. A batch that claims numbers still runs CI twice (unmeasured in other repos; none in
this repo, Oct 24 to 31). When only the page conflicts with the base, the tool rebuilds it on the merged tree.

A lane never commits a change to `docs/records.md`, not even one made by `lint/hook_catalog.py`. PR CI
already accepts a stale page (`lint/hook_catalog.py --check` waives it on a PR run). The guard `records-page`
refuses a lane commit whose staged `docs/records.md` differs from the page on the lane's base. A merge of
the base into the lane brings the base's page, so it is allowed. The guard needs no exception for the tool:
it judges Claude's own Bash commands, and the tool's commit runs inside the tool.

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
