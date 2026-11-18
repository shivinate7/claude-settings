# A blind designer brief has no branch slot

**What.** `skills/design-explore/blind-brief.md` has no branch line, and `hooks/blind_brief.py` has no read of one. A blind designer then has no branch to push to, and pushes nothing until the orchestrator names one. Step 6 of the skill says each brief names one branch per designer. Mistake: the orchestrator sends the template as it is. Harm: the designer's mockups reach no branch until the orchestrator adds one by hand. Reported 2026-11-09 (lane agent-branch-push-refuses); read again on main.

**Where.** `skills/design-explore/blind-brief.md`, and `hooks/blind_brief.py`.

**Decision.** `blind-briefs-use-a-template` (a blind brief follows one template).

**Retire.** The template holds a branch slot, and the hook accepts that line in a blind brief. A case in `hooks/test_blind_brief.py` passes a blind brief with a branch line, red on the current hook. Test file: `hooks/test_blind_brief.py`.
