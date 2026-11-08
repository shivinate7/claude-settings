# A later review round waits for the earlier round's reviewer

## The ruling

Coordinator, 2026-11-08 10:04 CST (roadmap step `review-rounds-in-order`, shape b): the guard refuses a reviewer spawn whose brief carries `Round N of 3`, N 2 or 3, while a reviewer of an earlier round on the same pull request still runs in this session.

- Rule `review-rounds-in-order`, decision deny, in `hooks/guard.py` (`round_order_hit`). The marker is read by `brief_markers`, the one marker scanner. A brief with no marker is round 1 and is never refused.
- The pull request is each `#<n>` the brief names, matched as a whole number. `#2038` does not match `#20380`. A brief that names no pull request is not refused.
- A reviewer runs while its call has no result, or its background launch (`async_launched`, with an agentId) has no terminal task notice. The notice is read by `stall_watch.closed_by_notice`, in the user and queued-command forms.
- A foreground reviewer whose call returned, and a spawn that a hook refused (an error result), do not run. A builder's `Round 3 of 3` is not a reviewer spawn and is not judged.
- The reason names the earlier round that runs and tells the session to wait for its notification, then spawn the next round.

## The incidents

- PR #2038: three review rounds ran at once on one head. Round 2 judged the head that round 1 was still checking.
- PR #1958: rounds 1, 2 and 3 ran in parallel. Round 1 failed and the head moved, so rounds 2 and 3 judged a head that no longer existed.

## The mistake and the harm

An orchestrator spawns round 2 or 3 before round 1 reports. A later round reads a head that the earlier round's findings will change. The round count is spent, and the owner reads reviews of a diff that is gone.

## The cost

One read of the session transcript for each round-2 or round-3 reviewer spawn. No read on any other call. No process starts, no file is written, and no log is added.

## The limits

- Fail open. A transcript that cannot be read, a bad line, or a failed import allows the spawn. A refusal needs a read that worked.
- It sees this session only. A reviewer that another session started is not seen.
- A brief that names the pull request in other words (a branch name, a URL) matches nothing and passes.
- A background reviewer that ended with no notice in the transcript still counts as running. The remedy is to wait for the notice or to stop it.
- It judges rounds of reviewers only. The model rows are in `agent-model-cap`.

Kind: build
Plan: docs/decisions/review-rounds-in-order.md#the-ruling (all)
