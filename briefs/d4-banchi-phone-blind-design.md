# d4: first design test, a blind pass at a true phone app for Banchi

Cloud design thread brief. Build advisor (10), Oct 27, against claude-settings main 6a3e842.
Ruling, Oct 27 11:45 CDT (shiv, waiting page item d4-first-design-test): a fresh, random pass at a
true mobile app for Banchi. /board and a home-app screen are dropped.

## Roles
One designer agent (Opus, agents/designer.md, the d1 role), then one design reviewer (Opus).
Designer and reviewer are separate agents.

## Task
1. The designer runs skills/design-explore blind, per c109's template: no current screen and no spec
   beyond the job. The job: "Bulk-list pre-sorted TCG singles on TCGplayer with zero attention per
   card, and know where every card physically is", on a phone. Read nothing in shivinate7/banchi.
2. Target the iPhone Duo folded first (c113), then unfolded.
3. Make three to five directions. Each one is a mockup with its named states (empty, loading, a full
   list, an error), as self-contained HTML plus a PNG per state.
4. Save them under the roadmap branch, designs/d4-banchi-phone/. Push nothing to banchi.
5. They reach shiv as pictures inline on the waiting page's Designs tab (d9). d9 lands in the next
   batch. If it is not on main when the designs are done, report that and stop. The build advisor
   adds the page item after the merge.

## Done when
The design reviewer passes each direction against docs/design. The report lists each direction in
one line, with its file paths. Report cap 15 lines. Port: the flow is global; the mockups are Banchi's.
