# A refuter brief that holds a prior refuter verdict passes

**What.** A refuter gives one verdict: `holds`, `revise` or `refuted` (decision plan-refuter). The blind-brief check reads only the reviewer verdict words, so a refuter brief that carries `Refuter: revise` or `Verdict: holds` passes. A refuter re-spawned on a revised plan can carry the prior refuter line pasted from the plan, so Claude hits it in normal work.

**Where.** `hooks/guard.py`, `REVIEWER_VERDICT_WORDS` and `BRIEF_BLIND_VERDICT`: both name only `PASS`, `FAIL`, `PARTIAL` and `CHANGES`.

**Decision.** reviewer-brief-blind (a reviewer's brief holds no report or verdict).

**Retire.** For a refuter role, the verdict check also reads `holds`, `revise` and `refuted` after a verdict or `Refuter` label. A case in `hooks/test_guard.py` shows that a refuter brief with `Refuter: revise` is refused, and that a reviewer brief using the word "revise" in prose passes.

**Fix.** step:refuter-verdict-words
