# Design agents

## The ruling

Owner, 2026-11-04 07:56 CST (Cockpit item 204 a): the design reviewer runs beside review round 1,
on the first built head, so design fixes ride the normal review rounds. Owner, 2026-10-26 (waiting-page
item 15, answer b): a lane that touches a screen gets two design agents, both on Opus, except a
text-only change (owner, 2026-11-03: design reviewer only).

- The designer (`agents/designer.md`) runs before the builder. It draws one HTML mockup per changed
  screen, with a notes file, in the repo's design folder (the `design` kind in `lint/layout.json`).
  home's `docs/design/` is the working pattern.
- The builder builds to the step's mockup when one exists (`agents/builder.md`).
- The design reviewer (`agents/design-reviewer.md`) runs beside review round 1, on the first built
  head. It judges each built screen against the mockup and the repo's design rules, at every size and
  theme, with a verdict per screen. Its fixes go to the builder with the round-1 code findings.
  - Owner, 2026-11-06 11:22 CST (owner item 259 a): any change to a screen file after review round 1
    gets a second design read.
  - Lane's reading, for the owner to correct: this covers each later review round and each fix check. A
    screen file is any file a screen is built from: markup, component, style, token or copy. In a second
    design read, the design reviewer alone reads the new head, on the screens that file renders. It
    judges against the mockup, or main's screenshots for a text-only change, and the round-1 blind
    list. No new blind pair runs. Its fixes go to the builder with that round's code findings. After a
    fix check, they go to the builder as one more fix, with its own fix check.
- Routing has one test, one exception: does the lane touch a screen (`roles-one-role-per-agent`). `agents/reviewer.md`
  still reviews the code. Exception: a text-only change skips the designer. The design
  reviewer still runs beside round 1. Owner ask `ask-mw18vywh8g` (small text changes on existing
  screens), 2026-11-03 16:13 CST.
  - A text-only change edits an existing screen's files and changes only user-visible copy. User-visible
    copy is text nodes, locale values, and an element's visible or read-aloud label, placeholder, title or
    alt. A class, style, token, icon name, URL, key or test id is never copy. It adds, removes or moves no
    element, class, style, token or layout, and adds no screen.
  - Outcome the designer protected: the new copy fits the screen, seen before the build. The design
    reviewer protects it now. It compares the built screen with main's screenshots of the same screen,
    at every size and theme, and catches overflow and truncation. It also catches a label, button or heading
    that newly wraps (it fit on one line before) from the new copy. It reads the built diff too: any element, class,
    style, token or layout change in a text-only change is a finding that sends the lane to a designer.
- The blind reviewers of `skills/design-review` stay blind. They keep agentType `reviewer` and never
  see the design spec. The design reviewer reads the spec, so it runs only at that skill's compare
  step, after the blind list is complete (`design-skills`). A second design read reuses the round-1
  blind list.
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

Reason: the owner wants each screen seen before it is built, and judged on the first built head against
what was seen. Beside round 1, its fixes ride the normal review rounds. In the degen repo, PRs 385 and
386, the design reviewer ran after review round 3 (owner, Cockpit item 204 a). A text-only change is the exception: no designer sees it first, and the design
reviewer judges it against main's screenshots. Reopen when the owner rules on `/design`, or when a design
agent's Opus cost shows in a cull.

Kind: process
Home: agents/designer.md
Home: agents/design-reviewer.md
Home: agents/reviewer.md
Home: skills/design-review/SKILL.md
Home: skills/design-explore/SKILL.md
