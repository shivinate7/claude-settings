# verdict is not on an agent's PATH

**What.** An agent cannot run `verdict` by name, because the agents' PATH does not hold it. The rule `tokens-run-through-verdict` asks every verification command to run through `verdict`.

**Where.** `bin/verdict`, and the agents' PATH that does not reach it.

**Decision.** cull-guard-wrong-refusals (the guard cull), which lists this gap.

**Retire.** Closed when `lint/test_verdict.py` runs `verdict` by name from an agent's PATH.
