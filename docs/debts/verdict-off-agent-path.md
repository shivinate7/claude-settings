# verdict is not on an agent's PATH

**What.** An agent cannot run `verdict` by name, because the agents' PATH does not hold it. This is a PATH issue, not a guard. The rule `tokens-run-through-verdict` asks every verification command to run through `verdict`. Source: a lane's report, which found that agents' PATH lacks `verdict`.

**Where.** `bin/verdict`, and the agents' PATH that does not reach it.

**Decision.** rule `roles-findings-are-debts-or-notes` (a known gap is a debt only if Claude is likely to hit it in normal work).

**Retire.** Closed when `lint/test_verdict.py` runs `verdict` by name from an agent's PATH.
