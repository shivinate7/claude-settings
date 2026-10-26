# c62: a one-act override pass lifts exactly one act on Windows too

Cloud build thread brief. Build advisor (2), Oct 26, against claude-settings main e5525a6.
Base: main e5525a6; never rebase onto main after review. Push roadmap edits to the branch only;
only the triage thread republishes the roadmap page.

## Incident

Main's push run 40273599923 (bf084df), gates-windows-guard: the case "override: two calls racing
for one one-act pass, exactly one gets it" went red. Six calls raced and two got allow. So a typed
one-act pass can lift a second act on Windows when tool calls run in parallel. A likely risk in
normal work (parallel calls in one turn). hooks/override_pass.py `take` spends a one-act pass by
`os.rename` to a unique name; on Windows a rename can succeed for two racers, or the read happens
before the claim. Unchecked: the exact cause. Find it, do not guess it.

## Task

1. Red first: repeat that case (and a six-racer variant) many times on windows-latest by a
   dispatch run of the branch, until it shows the double allow. Record the run id and the count.
   If it never goes red in a bounded number of tries, say so and still fix the read-then-claim
   order you can prove from the code.
2. Fix: make the claim atomic on every OS, with one primitive in override_pass.py: claim first,
   then read the claimed copy (for example `os.open(..., O_CREAT|O_EXCL)` on a claim marker, or
   rename into a per-racer name followed by a check that the source is gone). The loser denies.
   Keep the guard's fail-closed behaviour when the pass file cannot be read.
3. The same fix holds on Linux and macOS; their suites must stay green.

## Failure classes and proof

- Red then green on windows-latest, same repeat count, with the run ids in the PR body.
- Bypass: a pass must never lift two acts; a false alarm: a single caller must still get allow.
- It changes a guard: hooks/mutate_guard.py gets a mutant that drops the claim, and it must die.
- A fresh Sonnet reviewer reads the diff; net-value test only after round 3.

## Report

Cap 20 lines: Done, Deviations, Next. Send the green, reviewed head and branch to
"Advise the claude-settings build (2)". No question for shiv: park any in the PR body.
