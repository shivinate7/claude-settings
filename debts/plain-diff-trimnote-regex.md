# The trimNote table regex was not re-checked after round 3

- **What.** The table-row regex in `trimNote` was quadratic only on absurd input. It was not re-checked after the round 3 fixes. A long line of pipes, dashes and spaces is an example. The cost on real input is unmeasured.
- **Where.** The table-row regex in `trimNote` in `mods/plain-diff/hooks/lib.mjs`.
- **Decision.** `plain-diff-mod-limits` (plain-diff sends a diff to a model only past the secret filter).
- **Retire.** A timing case on a long line of pipes, dashes and spaces finishes under a set bound.
