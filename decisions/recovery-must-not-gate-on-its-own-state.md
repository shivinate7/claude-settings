# A recovery control must not gate on the state it recovers

CLAUDE.md's Verification paragraph now states this rule. This entry records the
evidence for it and where the rule came from.

## The principle

A recovery control exists for the moment its own precondition is false. Gate it
on that same state, and the gate blocks it exactly when it is needed. The gap
stays hidden until the day of loss, when the control is silent instead of
working.

## Evidence in this repository

This repository has no defect of this shape. It already follows the principle
twice, by design rather than by a written rule.

**Rule 1b, pointer-head.** The rule denies a command that moves HEAD off `main`
in the pointer checkout. A move TO `main` is the recovery act. The rule does not
deny it. It passes, and the invariant is restored. See the rule list and the
pointer-head rule in the `hooks/guard.py` docstring.

**The clone is not frozen.** Rule 7 freezes `hooks`, `lint`, `agents`, and
`state` under the config directory, and denies a session's own write there. The
clone of claude-settings on disk is a separate, unfrozen path. A hook that
breaks after landing can still be fixed at its source and reinstalled. See
`hooks/guard.py:1636`, "THE CLONE ITSELF IS NOT FROZEN."

## The outside measurement

The principle itself comes from a sibling repository, mailaudit. Its own
CLAUDE.md file records three incidents of this failure. One sat in a feature
called Backup. Two sat in a feature called Sync. Its own words: "any control
that recovers state must not be gated on that state existing. Backup was
widened once for this reason, Sync twice."

That count is mailaudit's own measurement, taken in its own codebase. It is not
a measurement taken in this repository. This repository holds no incident of
the shape. The two behaviours above are cited as evidence that this repository
already meets the principle, not as a defect the principle fixes here.

## The mechanism

Rule 1b and the unfrozen-clone test in `hooks/guard.py` are the mechanism for
this rule. No new code lands with this entry.
