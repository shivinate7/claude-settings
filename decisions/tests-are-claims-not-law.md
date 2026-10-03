# Tests are claims, not law

## The ruling, 2026-09-28

The owner said, in q_max:

```
remember to question any tests that may break our changes -- don't bend
over for stale rules without askng me first, treat tests and rules like
claims rather than law
```

q_max holds the same entry, cited as "q_max tests-are-claims-not-law". The owner adopted
the ruling for claude-settings on 2026-10-03, by their word in this session.

## The 3 classes

A change that breaks a test sorts into one of three classes.

1. **Re-point.** The subject still holds, and only its route changed. Re-point the check
   to the new route. Show it red on the old check, then green on the new one.
2. **Real defect.** The failure found a genuine bug. Fix the code, not the test.
3. **Stale rule.** The rule behind the test may no longer protect anything. STOP. Bring the
   owner the entry id, its gloss, and the stale sentence. Name the outcome the rule
   protected and what protects it now. Propose a fix. Wait for the owner's word, per
   `rule:outcomes-stale-decision-protocol`.

Every builder brief and every reviewer CHANGES verdict carries this list, so a test
failure never gets silently bent around.
