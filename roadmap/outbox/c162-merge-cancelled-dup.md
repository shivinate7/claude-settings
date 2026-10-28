# c162-merge-cancelled-dup

Status: ready. Draft PR #752. Head 13bacb86.

- Fix: `Host.classify` drops a "cancel" check row only when that name also has a "pass" or "pending" row. Cancel-only and cancel-beside-skip names stay red. Fail and timeout rows are never dropped.
- Tests: five new classify tests, each red first. The full merge suite, `ci-job gates --lint` and the silent-undo pre-check all pass.
- Review: round 1 (Opus) found the cancel-beside-skip bypass, now fixed. Round 2 (Sonnet) found a weak test, now fixed by the builder's try 3 (Opus). Round 3 (Sonnet) found no defects, and the net-value test was positive.
- Models: builder Sonnet, try 3 Opus; reviewers Opus, then Sonnet, then Sonnet.
- Note, not a debt: check rows are keyed by name only, so a job name shared by two workflows could hide one workflow's real cancel in the preview. This repo has one gated workflow.
- Deviation: the brief says "the newest completed non-cancelled run". The lane keeps every non-cancel row instead, so an older fail beside a newer pass still reads red. That is safer, and main already behaves that way.
