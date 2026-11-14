# The batch runner logs each session's spend at each batch merge

Step title: the heading above is the title of roadmap step `spend-log-per-batch`. It is not the owner's wording.

## The ruling

Owner, 2026-11-11 11:55 CST, relayed by the retrospective session. Exact words: "spend should also be logged if literally free to do so since it gives us more data about how we do things".

Ruling: spend is logged, if literally free to do so.

Duty (plan design): the build gives the batch runner the log only if the reads are literally free. Whether they are: unmeasured.

Plan design (restart plan 3.15), unruled: at each batch merge, the batch runner reads the `get_session` cost of each session and writes one line per session to the record branch.

The restart plan, section 3.15 ("Spend fewer tokens, measured first"), says `get_session` already returns each session's cost. This record did not run `get_session` to check that. That claim is unmeasured here.

## Readers

A log needs a named reader (the rule that a log needs a named reader, `outcomes-mechanize-rules`). Plan 3.15 names two readers. Neither is built.

- R33, every role has a chosen model and effort. Its model evaluation reads the log. The step that builds it is `model-table-one-home`, status todo.
- R34, the page shows how the system works and how healthy each part is. Its spend row reads the log. The step that builds it is `owner-health-tab`, status todo.

## Cost

Each batch merge costs:

- One `get_session` read per session (no test pins this count yet). It runs inside the batch runner's merge run, a process already running.
- One line per session on the record branch (no test pins this count yet).
- No timer, no new process, no watcher.
- The token cost of one read: unmeasured.

The owner asked for the log only if it is literally free. This record names no cost beyond the reads above. Whether those reads are literally free: unmeasured.

No test proves this cost yet. The build adds that test.

## Unruled

The line's format and file: unruled; the builder proposes it.

## Where the duty is written

The build writes this duty in the "Batch runner" bullet of `docs/decisions/session-tiers.md`. That bullet says what the batch runner owns. `skills/project-ops/templates/operating-model.md` restates a shorter version of the bullet for other repos' project instructions. It is a template, so `docs/decisions/session-tiers.md` is the home.

## Dated by

This record goes stale if `get_session` stops returning a cost, if R33 or R34 is dropped as a reader, or when either reader step ships. Then rewrite its Cost or Readers section in place.

Kind: build
Plan: docs/decisions/spend-log-per-batch.md#the-ruling (all)
