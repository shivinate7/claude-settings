# A mutant proves nothing until its own cause is checked

## The ruling

A test harness must not judge its tests by exit code or by "some output changed". Those are shapes of
failure. The act to check is that THIS suite fails BECAUSE of THIS mutation (predicate-is-the-act).

- In `hooks/mutate_guard.py`, every mutant carries a required case name. The verdict loop checks that
  name against its own red lines, not just their presence. A mutant whose FAIL lines miss the name it
  claims to break reports `WRONG CAUSE`. That verdict stays distinct from `SURVIVED`, and it fails the run.
- The mutant work directory carries a copy of the real, unmutated `guard.py` beside every `watch`
  mutant. `import guard` in `config_watch.py` then resolves to it, not to a crash.
- Verify a harness the way a gate is verified: name the case the change must produce, and confirm
  that case, never a shape near it.

Reason: a missing `guard.py` crashed all seven `watch` mutants before any watch logic ran, and the
generic "any red line" check still printed `KILLED` for each.

Kind: process
Home: hooks/mutate_guard.py

## Holes, named

Mutants other than the watch target are not audited for hidden
crashes. The required-name field narrows this risk. It is not proof against every crash shape.
