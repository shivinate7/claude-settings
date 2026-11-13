# Stalled steps

## The question

How does a roadmap step's shown state stay true? Owner, 2026-11-06 11:39 CST: "how can something be measured as doing and be a lie? … it needs to be somehow brought to the forefront mechanically so it can either be resumed or continued on or shown as paused."

## The ruling

- Nobody types a step's `doing` status. Triage's build (`skills/roadmap/build.py`) sets it from live PRs. GitHub Issues play no part. Ruling: owner 2026-11-11 16:44 CST, "agreed on p". p′ is the refuter's revised plan, in restart plan commit 69fb75f.
- Triage closes the stale drafts on build.py's upkeep list (the row "draft PRs over STALE_DRAFT_HOURS h with no live lane") once, then again at each batch. It skips any PR with a backlog-drain ledger row. The batch runner closes those, each with a comment (ruling `pr-close-by-batch-runner`, home: decision `session-tiers`, "Closing PRs").
- A `doing` or `active` step with no live lane is a **stalled step**. A live lane is a session in this repo tagged `cs-step` that is not completed or failed (idle and `review_ready` stay live), or an open PR on branch `<id>` or `lane/<id>`. Rulings: owner 2026-11-07 12:22 CST; coordinator 2026-11-07 12:33 CST and 14:40 CST.
- An answered waiting-page item whose lane is gone is stalled too.
- Each stalled step needs a disposition:
  - **resume**: a lane goes live.
  - **pause**: the step's `paused` field gives `why`, `decides` (owner, coordinator or triage), `at` (ISO time with zone) and `by` (triage).
  - **done**: status `done`.
- An unknown live read shows unknown. It never shows empty.

## Mechanisms

- `skills/roadmap/build.py` prints a `stalled step:` line for each stalled step. It exits 1 after it writes the page.
- The Status tab shows a stalled band.
- `lint/report_guard.py` holds triage's Stop while stalled entries stand. The first Stop with entries refuses unless an owner override is live. A Stop after a refusal (`stop_hook_active`) is released when Input Needed names every stalled id and item n, or when an owner override is live. A held Stop never carries the report's correction tail. A build run through `verdict` is read from the log file `verdict` printed. A verdict-run build whose log is missing or unreadable is skipped, and older entries stand.
- Owed, not built: `build.py` does not yet set `doing` from live PRs. It still reads the typed status.
- Owed, not built: a guard refuses a lane PR whose branch or title names no step id. A lane builds it after the fan-out.

## Coordinator rulings

Process picks, reported to the owner, 2026-11-06 11:48 and 12:49 CST:

- Triage clears the backlog from an audit before the hold merges.
- The hold sits in triage's Stop.
- A live `doing` step reads "In progress".
- `lane/<id>` counts as the lane.
- A `cs-topic` session counts as live for items only.
- Part 2, 2026-11-06 14:38 CST: the build lists ready-not-started steps (`todo` or `ready`, phase
  `now`, no live lane, no valid `paused` field, no open unanswered item). `ready` reads as todo. The
  `Unstarted:` refusal is held until a re-measure (debt `unstarted-guard-held`, the Unstarted guard
  is held).
- 2026-11-06 15:13 CST: `ready` reads as todo everywhere. A `ready` step that an open PR names gets
  the red pair line, as a todo step does.

## Cost

No process or timer. Per Stop, the hold adds:

- No stalled entry: no transcript read. It reuses the records the Stop already read.
- Entries: one own-record transcript read (`_own_tier_proved`) (unmeasured).
- A Stop after a refusal (`stop_hook_active`) with entries: that read, and one more for the Input Needed check (`last_reply`, since the hook carries no reply text).
- Each verdict-run build in the transcript: one log read (unmeasured).
- A build result in the transcript: `build.py` loads for its line prefix (unmeasured: no test counts the load).
- A lifted override: one claim-marker file, once per override (unmeasured).

`build` reads the live file triage already writes.

Kind: build
Plan: docs/decisions/stalled-steps.md#the-ruling (all)
Home: skills/roadmap/build.py
Home: lint/report_guard.py
