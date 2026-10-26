# d1 and d2: a designer agent and a design-reviewer agent, both on Opus

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main 3b96ce8.
Base: main 3b96ce8 (or the newest main when you start); never rebase onto main after review.
claude-settings only. Push roadmap edits to the branch only; only Triage the roadmap (3) republishes.

## Rulings

- shiv, Oct 26 (page item 15, b): Opus is allowed now for the designer and the design reviewer, a
  standing exception to roles-sonnet-is-the-ceiling for design and UX agents only. No proof run first.
- Deferred, not this lane: whether the designer runs Claude Code's /design canvas itself or shiv runs
  it. Build the HTML-mockup path below; leave a one-line "Deferred" note in agents/designer.md.

## Task

1. CLAUDE.md roles-sonnet-is-the-ceiling: add the designer and design reviewer to the Opus list, in
   the fewest words. Update subagent-model-cap (the model-per-role table) to match. One ruling covers
   both; record it in its decision home with the date and shiv's word.
2. agents/designer.md (Opus): for a lane that touches a screen, writes one HTML mockup per screen
   under the repo's design folder (from layout.json; home-app's docs/design/ is the working pattern:
   read it, do not copy files). Write scope: the design folder only. Add a write-scope guard only if
   an existing guard can be extended; one home per capability.
3. agents/design-reviewer.md (Opus): judges screenshots against the mockup and the repo's design
   rules, at every size and theme the repo ships (verification-screens-verdict), verdict per screen.
   skills/design-review names this agent. agents/reviewer.md stays as it is for code review.
4. agents/builder.md: one clause, the builder builds to the step's mockup when one exists.
5. Routing: one test, does the lane touch a screen. Put it where the orchestrator picks roles.

## Failure classes and proof

- Test-author first, red on main: the model-cap check (or the guard that asks before an Opus spawn)
  allows Opus for designer and design-reviewer, still asks for any other agent (false-alarm and hole
  cases both); a designer write outside the design folder is refused if a guard is built.
- rule_audit's pinned counts move only by new anchors; say which bucket.
- Run every gates.yml step locally before sending.
- A fresh Sonnet reviewer reads the diff (it changes a rule and a guard).

## Report

Cap 20 lines: Done, Deviations, Next. Include "Port to other repos: yes or no, and why".
Send the green, reviewed head and branch to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft. Park any question for
shiv in the PR body.
