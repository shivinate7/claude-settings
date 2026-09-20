# A gate's allow list is the constant

CLAUDE.md says: "Once set up, turn each rule below into a hook or check." A gate
built from a copy of the rule drifts away from the rule. Point the gate at the
constant the code already reads. Then one edit widens both, and the thinking
lands where the widening happens.

## The failure a copy produces

A gate holds a list of what it permits. The code holds a list of what it emits.
When those are two objects, an edit to one leaves the other behind. The gate then
passes the case it exists to refuse, and it reports green while it does so.

Nothing announces the drift. The gate still runs. The suite is still green. The
only signal is the leak itself, later, in a place that keeps it.

## The evidence

`~/Developer/mailaudit` builds a public page that carries a snapshot of a private
ledger. A check decodes the built page and refuses any key outside the permitted
set. Its own CLAUDE.md records the choice:

```text
Its
allow-list is `SEED_KEEP` itself rather than a copy, so widening the seed
widens the gate in the same edit - deliberately, since that edit is where the
thinking should happen.
```

The same entry is honest about the limit, which is the second half of this rule:

```text
It is a backstop, not a proof: it can only refuse the leaks someone already
thought of, which is why the hand grep stays the instruction.
```

The leak that produced the check was found by decoding the built artifact, not by
reading the source that meant to write it. So the gate reads the artifact, never
the intent.

## How to apply it

Import the constant. Do not restate it. Sometimes the gate cannot import it,
because it runs in another language or another process. Then make the build emit
the constant, and make the gate read what the build emitted. A second literal is
the thing to remove.

Then prove the gate. CLAUDE.md: "Trust a guard only once it goes red on the
defect it guards." Widen the constant by one key, run the gate, and watch it
pass. Add a key to the artifact alone, run the gate, and watch it fail.
