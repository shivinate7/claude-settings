# A push to a pull request's branch needs the review log of the last round

## The ruling

Rule `handed-in-push-needs-record` in `hooks/guard.py` refuses a `git push` to the branch of an open pull request. It refuses while the pull request's newest review log is for an older head than its live head on GitHub. Owner pick a, step `handed-in-push-needs-record`. The verdict is `handed_in_push` in `merge/merge.py`, built on `live_review_state`, the one home of the stale review log read. The guard call is `handed_in_push_hit` in `hooks/guard_merge.py`. It reads the pushes as the force-push loop does (`_push_calls`: `bash -c` and command substitutions included) and runs before that loop's ask, so no answer to the ask skips it. It reads each push's words as written, so a quoted substitution stays a word. The pull request is read through `Host.batch_pr`, the one home of that read.

- The mistake: lane page-grant pushed to a handed-in branch twice before the review log of the last round was posted (coordinator, 2026-11-14 16:37 CST, n=1 lane, twice).
- The harm: each push moves the head. The review log of the head the round reviewed goes stale, and the next merge needs a new round that nobody owes.
- A hit: the newest review log of the pull request of this repo that holds the pushed branch is stale at the live head. No clean merge of main and no records-page commit of the merge tool carries it there. A fix push after a FAIL round hits when the review log of that round is for an older head.
- Allowed: a pull request with no review log, which is the known gap of option a: a first round has no review log to be stale. A review log for the live head, a FAIL round too. A clean merge of main, and the merge tool's own records-page commit. A branch no open pull request holds. A destination named `main` or `master`, which keeps the `push-main` ask. A dry run. A repo that does not use the merge tool.
- A newest review log that does not parse, or names another pull request, is unknown: the push is refused. An older valid review log does not carry it.
- A push whose branch the check cannot name is unknown: a destination held in a shell variable or a substitution, a destination the config leaves open (`push.default=matching`, a detached head), a glob refspec, and `--all`, `--branches` or `--mirror`. Only the remote and refspec words are read for this. A redirection or a pipe after the push is no destination. A push that only deletes or sends tags moves no head and passes. A delete beside a refspec that sends does not hide that refspec: it is judged.
- A push whose folder is a shell variable (`git -C "$WT"`, `cd "$WT" &&`) is unknown: its remotes cannot be read. A literal folder that is not there fails git before it sends, so this check leaves it to the force-push ask.
- Only a push to origin counts, the remote the merge tool and `gh` read. A push to another configured remote passes. A remote named by a URL or a path that is not origin's own spelling is unknown. A pull request whose head branch is in a fork holds no branch of origin: it is not held.
- An open pull requests read that cannot run names no pull request, so no review log is stale: the push is allowed, and the guard prints one stderr line that says the read is unknown. An unloadable merge tool counts as that read.
- A read after a pull request is found refuses as unknown, by this decision: the comment read, a commit read, or the compare of a clean merge. Two open pull requests on one branch are unknown too. The reason says the read is unknown and never reads as a review log that is absent.
- Departs from: decision `guard-hooks-fail-closed`, where a guard read that cannot run refuses. Here an open pull requests read that cannot run allows the push. That decision covers a guard that crashes or times out, not a lookup that names no pull request (lane call, 2026-11-15 01:59 CST; not an owner grant).
- The remedy has the review log posted for the live head, then the push retried. It names no branch.
- Step `fix-push-needs-fail-record` folds into this check: its FAIL-round case is this check with a FAIL review log, and it needs no second check (`building-one-home-per-capability`).
- Not read: a claim commit on top of the reviewed head (the call passes no stamp config to the walk), so a push over one reads stale. The merge tool pushes claims at the join, not a lane. MCP file writes (`create_or_update_file`, `push_files`), which move a pull request's head with no `git push` (a note in the debt store).
- Cost, unmeasured: per pushed ref one paged read of the open pull requests (gh REST), unmeasured. A named remote costs one `git config --get-regexp` (unmeasured), and a remote named by a URL or a path one `git config --get` (unmeasured). When a pull request holds the branch, one paged read of its comments is unmeasured too. One commit read per commit walked for a stale review log is unmeasured too. One compare per merge is unmeasured too. All share `MERGE_READ_TIMEOUT`. No log, file or process stays.

Protected by the `handed-in-push` cases in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py
