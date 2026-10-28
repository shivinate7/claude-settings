# Design agents

## The ruling

Owner, 2026-10-26 (waiting-page item 15, answer b): a lane that touches a screen gets two design
agents, and both run Opus.

- The designer (`agents/designer.md`) runs before the builder. It draws one HTML mockup per changed
  screen, with a notes file, in the repo's design folder (the `design` kind in `lint/layout.json`).
  home's `docs/design/` is the working pattern.
- The builder builds to the step's mockup when one exists (`agents/builder.md`).
- The design reviewer (`agents/design-reviewer.md`) runs after the build. It judges each built screen
  against the mockup and the repo's design rules, at every size and theme, with a verdict per screen.
- Routing has one test: does the lane touch a screen (`roles-one-role-per-agent`). `agents/reviewer.md`
  still reviews the code.
- The blind reviewers of `skills/design-review` stay blind. They keep agentType `reviewer` and never
  see the design spec. The design reviewer reads the spec, so it runs only at that skill's compare
  step, after the blind list is complete (`design-skills`).
- Opus is a standing grant for both roles, a class-level exception to `roles-sonnet-is-the-ceiling`,
  with no proof run first. The model table is in `agent-model-cap`.
- Deferred: whether the designer runs Claude Code's `/design` canvas itself, or the owner runs it.
  Until the owner rules, the designer draws HTML mockups only.

Owner, 2026-10-27: "a lane or two of totally blank and a lane that gets to see the old and then some
in between with directed prompts ... to get a good mix of control and idea between the mockups."
A design exploration spreads its mockups across blind, informed and directed designer lanes. The
procedure is `skills/design-explore/SKILL.md`.

## The guard

Guard rule `designer-scope` (`hooks/guard.py`) refuses a designer's Edit or Write on a repo path
outside the design folder. A path in no repo, and the agent's own scratchpad, stay allowed. It
extends the role scopes of `builders-cannot-edit-tests`, and logs a designer's diff at commit and
stop the same way (`designer-diff`). Risk: likely. A designer that writes product code becomes a
second builder, unreviewed as one. Landed 2026-10-26.

Reason: the owner wants each screen seen before it is built, and judged after against what was
seen. Reopen when the owner rules on `/design`, or when a design agent's Opus cost shows in a cull.

Kind: process
Home: agents/designer.md
Home: agents/design-reviewer.md
Home: skills/design-explore/SKILL.md
