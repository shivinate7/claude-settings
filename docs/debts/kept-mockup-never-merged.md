# Kept mockups never reach a main branch

- **What.** A mockup the designer keeps reaches no main branch. The designer pushes only its own branch, and design-explore gathers the kept mockups onto a design branch with no PR step. Measured 2026-11-02: 3 claude-settings mockups exist only on a non-main ref. q_max, banchi, degen, mailaudit and joyous show 0.
- **Where.** `agents/designer.md`: the push step (line 82) and the write scope (lines 14-15), which limits writes to the repo that spawned the designer. `skills/design-explore/SKILL.md`: step 6, Gather (lines 67-68).
- **Decision.** `waiting-data-in-repo` (git is each artifact's home, and a mockup is an artifact too).
- **Retire.** The designer and design-explore open one PR of the kept mockups into the target repo's `docs/design`. The brief names the target repo. Check: none yet. Add one that a kept mockup is on the target repo's main after its PR merges.
