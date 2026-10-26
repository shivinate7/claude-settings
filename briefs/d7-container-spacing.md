# d7: space with containers, not margins

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main 853b512.
Base: main 853b512; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Task

Land the spacing rules in `ux/`, the design rules every child repo's screens follow:
1. Spacing lives on the parent: `gap` on flex and grid containers, never a margin on a child
   to space it from its siblings.
2. Page layout uses a few named layout primitives (stack, cluster, sidebar, grid or similar)
   and screen breakpoints. Name them and give each one CSS example.
3. A shared component adapts to its box with container queries, not the screen, so one
   component serves a sidebar and a main column with no copy (o11, one home per shared
   thing). Add a container breakpoint only where the component changes shape: each one is one
   more state to screenshot.
4. Fluid spacing uses `clamp()` tokens; put the token shape in `ux/tokens.md`.
5. Swift: the same intent with its own tools (ViewThatFits, size classes, stack spacing).

Point `skills/design-review` at the new section so a review checks it.

## Fences

- Docs and the design-review skill only. No new lint or guard: rule
  building-guard-needs-incident needs an incident or a likely risk, and none is named. The
  per-file ratchet seen in banchi does not spread (shiv, Oct 26); it stays out unless it
  earns its own case, which you may argue in the PR body.
- Read banchi, q_max, mailaudit and home-app for examples only; never push to them.
- o12 (skills up to date) runs at the same time and may touch design-review wording; keep
  your design-review edit to one pointer line.

## Failure classes and proof

- Each rule names the outcome it protects (centered content, no gap drift between screens).
- Run ste-changed and the markdown lint through `verdict`.
- Docs only: merges on green with no reviewer, unless you change a skill's behaviour.

## Report

Cap 15 lines: Done, Deviations, Next. Send the green head and branch to
"Advise the claude-settings build (3)". Do not merge, and do not rebase onto main. No
question for shiv: park any in the PR body.
