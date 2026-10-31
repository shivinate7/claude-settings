# One records index page, rebuilt by the merge tool before ready

## Ruling

Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and
debt with a one-line gist. Only the merge tool rebuilds the page. A branch never edits the page by hand.

The tool rebuilds the page on the integration branch before the branch goes ready: `merge <pr> --prepare`.
It runs on a draft PR only, and only when the head holds the base tip. It commits the page alone and pushes
it, so the branch is final at ready. Then the ready run is the merge run, and `--confirm` finds the page
current and pushes no commit. `--prepare` claims no record numbers and takes no merge lock.

`--confirm` still rebuilds the page and claims record numbers under the merge lock. A page that is current
makes no commit. A stale page (no `--prepare`, or the base gained a record since) gets the rebuild commit, and
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
of 50 merges to main, Oct 24 to 31, ended on that commit and ran CI twice.

Kind: build
Plan: docs/decisions/records-index-at-merge.md#ruling (all)
Home: lint/hook_catalog.py
