# The stamp check does not read a shallow checkout

**What waits.** `stamp.mjs --check` off the default branch needs the full history. A check job
sets `fetch-depth: 0`. A depth-1 checkout of a pull request's merge commit has no parents. So
the check cannot find the merge base, even with a shallow fetch of the base branch.

**Why it waits.** The owner ruled on 2026-09-28 to use full history for now. A large repo pays
for this in checkout time only.

**The idea, UNMEASURED.** On a pull request's merge commit, use its first parent as the base.
That needs only `fetch-depth: 2`. It needs a fixture that makes a shallow clone of a real
two-parent merge commit before anyone relies on it.

**Trigger that brings it back.** A repo reports that a full-history checkout is too slow for
its check job.

**Owner.** The claude-settings orchestrator that takes the next stamp change.
