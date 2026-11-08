# Stalled steps

## The question

How does a roadmap step's shown state stay true? Owner, 2026-11-06 11:39 CST: "how can something be measured as doing and be a lie? … it needs to be somehow brought to the forefront mechanically so it can either be resumed or continued on or shown as paused."

## The ruling

- `doing` is derived from live work, not typed.
- A `doing` or `active` step with no live lane is a **stalled step**. A live lane is a session in this repo tagged `cs-step`, or an open PR on branch `<id>` or `lane/<id>`.
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
