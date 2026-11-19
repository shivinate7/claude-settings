# One records index page, rebuilt by the merge tool before ready

## Ruling

Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and
debt with a one-line gist. Only the merge tool rebuilds the page. A branch never edits the page by hand.

Until the cutover (decision `all-repos-switch-together`), the tool rebuilds the page on the integration branch before the branch goes ready. After it, the tool rebuilds the page on each lane branch before that PR merges. `merge <pr> --confirm`
on a draft PR is that step (`draft_step`), and it never merges main. On the default base, it refuses a head that
conflicts with the base or cannot be read (`holds_base`), and a head whose last commit carries a Record-claim (`head_claim`). It commits the page
alone, pushes it, and stops: mark the PR ready, then run `--confirm` again. A head that lacks the tip but merges
cleanly is not refused. `merge <pr> --ready` runs the same step with `merge_main=True`. On the default base, it first
merges origin/<base> into a head that lacks the tip and merges cleanly (`merge_base_in`; owner ruling
`own-840-a-ready-merges-main-skip-page-commits`, page item 840 a, 2026-11-14 19:56 CST; ruling file on branch
`roadmap`). Any merge and any stale page commit go out in one plain push. Neither command merges a pull request.
The batch runner readies a PR only with `merge <pr> --ready`, never by a bare MCP or `gh` mark.
A mark that skips the step leaves the page unrebuilt. `--confirm` then refuses it and costs a second CI run (PR 3255 and PR 3472, 2026-11-15).
The tool sends no GraphQL, so its own mark is always refused (`Host.ready`). A successful `--ready` exits 0 and prints "stays a draft (".
So the ready route has three steps, in this order. One: `merge <pr> --ready`, which does what its help text says (merge main when the head lacks the tip, rebuild the page, run the declared ready checks, push when anything changed). Two: after the draft run of the head shows, the runner marks the PR ready by its session's route (route pr-ready-mcp-cloud). Three: `merge <pr> --confirm`. The tool's printed hint gives steps two and three (skill
ci-hygiene). So the branch is final at ready, and the ready run is the merge run. The step claims no
record numbers. It takes no merge lock. A PR that turns draft after the first read is the one case: the step runs
under the lock that confirm already took, and releases it.
The same two allow rules cover both steps, so no new rule is needed.

Take a ready PR on the default branch with no record number to claim or resume. Unless the base sets requiredChecks "none" (below), when its rebuilt page would
change the tree, `--confirm` refuses before any wait, claim or push. The refusal and the preview name
the remedy: return the PR to draft (route pr-draft-mcp-cloud), run
`merge <n> --confirm` on the draft, then mark it ready after its draft run shows. A head that holds a
Record-claim on a base with no stamp kinds first reverts that claim commit, since the draft step refuses a
claim head. A push that changes only docs/records.md after a head whose run was fully green starts no
second full run of the jobs. CI scope turns off the job and suite flags for that push
(owner, 2026-11-14 15:02 CST, ruling own-830-c, the records-only CI skip; `.github/scripts/ci-scope.sh`,
`green-head.sh`). Owner item 857 b (waiting-page save, 2026-11-15 19:48 CST, "Overrule: the ruling reopens")
holds ruling own-830-c again. The owner's answer of 2026-11-18 18:54 CST (relayed, "yes they can") narrows it: a suite step that reads a .md file may skip on a records-only push when the prior head's run was fully green. A lint step that reads the changed text keeps running. The all-jobs-passed rollup passes when those lint steps succeed. The `scope`, `nightly-skip` and `push-skip` jobs still run to decide it.
The job and suite flags cover the macOS, Windows, pointer, guard, shoot, mutation and sweep work. CI scope also turns
off the mutation report. The merge
tool heals a ready PR's stale page itself under merge.requiredChecks "none" (page item 926 a, 14:32 CST, 2026-11-16;
ruling own-merge-on-lint-pass, 2026-11-15 18:21 CST): one `--confirm` merges the base in when the base gained a record,
pushes one page commit, waits only for GitHub to show the pushed head, and merges that sha. A base that moves after the
push refuses and keeps the commit. Under a named list or "protection" it still refuses a ready PR with a stale page,
and the records push before ready stays. A current page makes no
commit. A claim stays at confirm under the lock, so its numbers are free on the base tip, as before. The
claim commit carries the rebuilt page, so the claim and the page share one commit.
One full `checks` run after the records step took 44 min (run 43583006785, PR 3349 head 3128df369, 09:58:07Z to
10:42:39Z by the GitHub REST read; n=1). Other repos are unmeasured. The page changes in about 1 of 3 to 1 of 2
PR merges (triage's approximate walk of PR merges, two overlapping windows: 4 of 11 since Nov 13, 20 of 38 since
Nov 10). The draft step refuses a claim head,
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
