# o10: a page per session for questions waiting on you (plan only)

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main d741cd5.
Base: main d741cd5; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Task

Write the design as a plan, plans/o10-session-questions-page.md, in one PR. Build nothing yet.
The plan answers the step's ask: what a session publishes, how shiv answers, and how the
answer gets back to the session.

1. Read first: the step note (roadmap/data/steps/o10.json on the roadmap branch), c31 and c28
   (how a question reaches shiv today: the desktop banner, rule questions-go-to-owner, the
   one-click command rule in output-styles/shiv-stylisms.md), and o8's note (the lasting repo
   page; keep o10 apart from it).
2. Measure, do not guess: what the Artifact tool and its runtime capabilities offer a session
   today on Max, on Enterprise and on an API key (publish, comments sent to Claude, shared
   state). Mark each fact checked or unknown, with where you checked it.
3. Design the "Copy answers" path first (works on Max and Enterprise): the page lists each open
   question with its options and recommendation; shiv picks; the page builds one block to paste
   back into the session. Then the Enterprise path (comments sent to Claude).
4. Give each choice that is shiv's as options with a recommendation, under a "Deferred for
   shiv" heading. Do not ask him now.
5. Name the cost per rule outcomes-mechanize-rules: processes started, files written, how often.
   No watcher, no timer (c26).

## Fences

- Plan only: no hook, skill, mod or rule change. A plan that needs a new rule names it.
- Overlaps: o8 (living repo page) and c68/design-review are other lanes; do not edit them.

## Failure classes and proof

- Every claim about the Artifact platform is checked or marked unknown.
- ste-changed through `verdict`. Plan only: merges on green with no reviewer.

## Report

Cap 15 lines: Done, Deviations, Next, and the Deferred-for-shiv list in one line each. Send the
green head and branch to "Advise the claude-settings build (3)". Do not merge, and do not
rebase onto main.
