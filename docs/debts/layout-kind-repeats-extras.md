# A new layout kind breaks repos that list it as an extra

- **What.** When `lint/layout.json` gains a kind that a rolled-out repo already lists in its `.claude/layout-extras.json`, `layout.kinds()` refuses that repo's extras file and ste_lint exits 2 on every lane there. Kind `map` did this to q_max on 2026-11-01. The refusal now names the remedy, but nothing finds the repo before it breaks.
- **Where.** `lint/layout.py` `kinds()`, and each change that adds a kind to `lint/layout.json`.
- **Decision.** `one-layout-every-repo` (the one layout, and extras that may not replace a layout kind).
- **Retire.** A check, or a step in the change that adds a layout kind, searches the rolled-out repos' extras files for that kind's name and opens their delete lanes in the same batch. A test shows the check red on an extras file that lists the new kind.
