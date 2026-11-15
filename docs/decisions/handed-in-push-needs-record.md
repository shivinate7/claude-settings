# A push to a pull request's branch needs the record of the last round

## The ruling

Rule `handed-in-push-needs-record` in `hooks/guard.py` refuses a `git push` to the branch of an open pull request. It refuses while the pull request's newest review record is for an older head than its live head on GitHub. Owner pick a, step `handed-in-push-needs-record`. The verdict is `handed_in_push` in `merge/merge.py`, built on `live_review_state`, the one home of the stale-record read. The guard call is `handed_in_push_hit` in `hooks/guard_merge.py`, beside `octopus_push_hit`, which shares its push reader (`_push_refs`).

- The mistake: lane page-grant pushed to a handed-in branch twice before the last round's record was posted (coordinator, 2026-11-14 16:37 CST, n=1 lane, twice).
- The harm: each push moves the head. The record of the head the round reviewed goes stale, and the next merge needs a new round that nobody owes.
- A hit: the newest record of the pull request that holds the pushed branch is stale at the live head. No clean merge of main and no records-page commit of the merge tool carries it there. A fix push after a FAIL round hits when that round's record is for an older head.
- Allowed: a pull request with no record, which is the known gap of option a: a first round has no record to be stale. A record for the live head, a FAIL round too. A clean merge of main, and the merge tool's own records-page commit. A branch no open pull request holds. A destination named `main` or `master`, which keeps the `push-main` ask. A dry run. A repo that does not use the merge tool.
- A newest record that does not parse, or names another pull request, counts as no record: the push passes.
- A read that cannot run refuses as unknown (`guard-hooks-fail-closed`): the pull request list, the comment read, a commit read, or the compare of a clean merge. The reason says the read is unknown and never reads as a record that is absent.
- The remedy has the review record posted for the live head, then the push retried. It names no branch.
- Step `fix-push-needs-fail-record` folds into this check: its FAIL-round case is this check with a FAIL record, and it needs no second check (`building-one-home-per-capability`).
- Not read: a claim commit on top of the reviewed head (the call passes no stamp config to the walk), so a push over one reads stale. The merge tool pushes claims at the join, not a lane. A push to a remote other than the one the pull request lives on.
- Cost: per pushed ref one paged read of the open pull requests (gh REST). When a pull request holds the branch, one paged read of its comments, and for a stale record one commit read per commit walked and one compare per merge. All share `MERGE_READ_TIMEOUT`. No log, file or process stays. Unmeasured.

Protected by the `handed-in-push` cases in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py
