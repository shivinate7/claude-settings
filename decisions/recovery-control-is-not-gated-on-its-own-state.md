# A recovery control is not gated on its own state

CLAUDE.md says: "A capability no user can reach is not built." A control that
recovers state is the sharpest case of that rule. Gate it on the state it
recovers, and it disappears at the one moment it is needed. This entry records
three times one repo paid for that, and why the pattern is general.

## The shape

A control that restores, imports, pulls, or backs up exists for the bad day. The
bad day is the day the state is empty, corrupt, or gone. A condition of the form
`items.length > 0` reads as "do not show a control for a list that is not there".
It means "hide the escape hatch while the user is trapped".

The test is one question. If this control worked, what state would it produce?
When the answer is the state in the gate, the gate is wrong.

## What it cost, three times

The evidence is `~/Developer/mailaudit`, a single-page ledger with a GitHub
backup. Its own CLAUDE.md records each case.

```text
**The file actions are gated on `items.length > 0 || envelopes.length > 0`, the
same condition as the view switch - not on `items.length` alone.** They used to
be, which meant a user holding hand-typed orphaned envelopes with an empty item
list had no Backup button at all, for data that exists nowhere else. Test 23.1.
```

```text
**And the whole region is gated on `... || !!window.remote`, wider still.** Same
bug, one level out, found on the live site the day Push/Pull shipped: an empty
ledger is *exactly* when Pull is needed - a new phone, ITP having cleared
storage, a move to another origin - and gated on data alone, the one control
that recovers from having no data was unreachable whenever you had no data. The
only button on screen was "Choose file".
```

```text
The History cell is gated on the versions **adapter**, never on the ledger: it
holds the one control that undoes a Reset, and gating it on `items.length` would
make it unreachable exactly when a Reset has just happened.
```

The same repo states the lesson it drew:

```text
The pattern to take from this: any control that *recovers* state must not be
gated on that state existing. Backup was widened once for this reason, Sync
twice.
```

## Why a test suite does not catch it

Every fixture in that repo booted a ledger with data in it. The suite was green
and the feature was broken in the one scenario that matters. The repo records
that too, as a method note. A gate on emptiness is invisible to a fixture that is
never empty.

So the check is a reading, not a test run. Find each control that recovers state.
Read its render condition. Ask what state a success would produce.

## What this does not say

A control that only edits present state may be gated on that state. A filter over
an absent list is noise. The rule covers recovery, not every control.
