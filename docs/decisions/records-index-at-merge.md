# One records index page, rebuilt by the merge tool before ready

## Ruling

Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and
debt with a one-line gist. Only the merge tool rebuilds the page. A branch never edits the page by hand.

Until the cutover (decision `all-repos-switch-together`), the tool rebuilds the page on the integration branch before the branch goes ready. After it, the tool rebuilds the page on each lane branch before that PR merges. `merge <pr> --confirm`
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
claim commit carries the rebuilt page, so the claim and the page share one commit.
After a stale-page refusal, the second CI run was timed at 70 min, n=2 timed runs in this repo (runner 10, PR
3349). Other repos are unmeasured. The page changes in about 1 of 3 to 1 of 2 PR merges (triage's approximate walk
of PR merges: 4 of 11 since Nov 13, 20 of 38 since Nov 10). The draft step refuses a claim head,
so the claim cannot move earlier. A resumed claim with a stale page still pushes the page, for the same
reason. When only the page conflicts with the base, the tool rebuilds it on the merged tree. That heal is
unchanged. Owner ask to stop the double CI run: Oct 31 14:12 CDT, repeated Nov 1 20:51 CST.

A lane never commits a change to `docs/records.md`, not even one made by `lint/hook_catalog.py`. PR CI
already accepts a stale page (`lint/hook_catalog.py --check` waives it on a PR run and on a dispatched run of a branch other than main). The guard `records-page`
refuses a lane commit whose staged `docs/records.md` differs from the page on the lane's base. A merge of
the base into the lane brings the base's page, so it is allowed. The guard needs no exception for the tool:
it judges Claude's own Bash commands, and the tool's commit runs inside the tool.
The guard runs before the generator, so it cannot tell whether a chained `generator && git add && git commit`
will change the page. It refuses such a chain even when the page ends unchanged. The refusal is exact for what
it can see.

A merge commit of a past base tip is allowed too. A lane merges the base, takes the page the merge brought,
and the base then moves on, so that page is no longer the base's. The guard allows the commit when the page it
would hold has the exact blob id of the page at MERGE_HEAD, and one of two things holds. One: MERGE_HEAD is a
commit on origin/<base>'s first-parent line (a past base tip). Two: some best merge base of HEAD and MERGE_HEAD (`merge-base --all`) is no
ancestor of origin/<base>. Two is a stacked lane: it was cut from a branch that main has not merged, and
MERGE_HEAD is that branch moved on. A lane cut from main has every best merge base on main, so it gets no pass
from two. Two cannot tell the lane's base from a sibling lane that shares its unmerged history. A sibling's page
passes the same way, and the merge tool rebuilds the page before ready.
A commit in the base's history off that line, such as a lane branch already merged into the base, is refused. A
rebuilt page, a page of a merge of any other commit, a page taken after `merge --quit` are refused. A failed
MERGE_HEAD page read or first-parent read refuses the commit. A failed merge-base read, or an is-ancestor exit
other than 0 or 1, gives no pass from two and falls through to one. Every other failed read stays no hit. The guard runs before the chain, so it reads the page as
it stands at the hook.
Cost: three more git reads, `rev-parse MERGE_HEAD MERGE_HEAD:docs/records.md`, `merge-base --all HEAD MERGE_HEAD` and
`rev-list --first-parent origin/<base>`, plus one `merge-base --is-ancestor <merge base> origin/<base>` per best merge base (unmeasured). They run only
on a commit the guard would otherwise refuse, so an allowed commit and a commit with no records page make the
reads they made before. The rev-list prints one id per base tip, under the 10 s read limit, and a timeout is a
refusal. No file, no timer, no new process beyond those git calls. Measure: the `records-page` family has 92
cases (`hooks/test_guard.py`); how often a real lane hits it is unmeasured. A chain that rewrites the
page before its commit is judged on the page as it stands at the hook, not the page the chain leaves (debt
note `records-page-chain-edit-after-read`, the same class as the base-page pass). A chain
that takes MERGE_HEAD's page into a tree that does not hold it yet is refused; split calls pass.

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
