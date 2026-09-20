# What a mutant tells you

CLAUDE.md says: "Trust a guard only once it goes red on the defect it guards."
Running the mutant is the first half. Reading the result is the second. A mutant
that lives and a mutant that dies each carry a finding, and both are easy to
misread. This entry records the two readings, because `hooks/mutate_guard.py`
runs exactly this test in this repo's CI.

## When a mutant lives, find the state your fixtures never reach

A surviving mutant is rarely a missing assertion. It is usually a missing state.
The assertions are fine. Every fixture simply ends somewhere the defect does not
show.

`~/Developer/mailaudit` records the case that taught it:

```text
**One mutant survived the first draft of group 40, and finding out why is the
lesson.** "The signal is never consumed" passed all fifteen assertions,
because every one ended with the two ends *in step*, where no further merge is
possible and a flag left standing costs nothing. The state nothing reached:
`check()` re-runs on every `syncBusy` flip, not only on visibility, so an
unconsumed flag lets the other device's push land mid-session with no resume
in sight.
```

So the move is not to add an assertion to an existing fixture. The move is to
build the state no fixture builds, and assert there.

The same repo found a second shape of it. One tier of a pruning rule could be
deleted with the suite still green. A different tier kept the same record, for
its own reason. When one rule keeps a thing, neutralise every other rule
before you claim which one did it.

## When a mutant dies, check the cause

A dead mutant proves an assertion failed. It does not prove the right assertion
failed. Read which one.

```text
- **The photo-ordering mutant was "caught" for the wrong reason.** It failed
  34.7 (the merged ledger reaching GitHub) because moving the code also tripped
  the generation guard - nothing was asserting about photos at all. It only
  became a real test once 34.31 put the blob **exclusively on the remote**...
  When a mutant dies, check it died of the right thing.
```

A mutant that dies of a side effect leaves the real behaviour untested, and it
leaves you believing the opposite.

## Two more readings from the same work

An assertion that throws is a worse kill than one that fails. A throw inside a
suite with no isolation aborts the run and hides every group after it. Guard the
read, so the assertion fails and the rest still runs.

A pair of mutants can be needed to pin one rule. The same repo records three
cases where each of two assertions is alive only against the mutant the other
misses. A single surviving mutant is therefore not proof of dead code.
