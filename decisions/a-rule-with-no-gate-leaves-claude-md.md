# A rule the owner took off the gate leaves CLAUDE.md too

On 2026-09-28 the owner ruled that the semicolon line leaves `CLAUDE.md`. The owner's
words, verbatim: `same with whichever else we emchanically eliminated, it doens't need a
prose inclusion in claude.md either then`.

## The sentence this changes

`semicolon-and-gendered-pronoun-rules-leave-the-gate`, the semicolon rule leaves the
linter, said: "Its guidance stays in CLAUDE.md as one line of prose, and no machine checks
that line." That line was "Never use a semicolon. Write two sentences." It carried the
anchor `output-no-semicolon`. The line, the anchor and its row in
`lint/rule_mechanisms.json` now go.

## What else this covers, MEASURED on main (d50ac23)

The owner also took the gendered-pronoun rule (STE018) and eight other STE rules off the
gate. None of them has its own line in `CLAUDE.md`. They sat under "Write in Simplified
Technical English by default", and that line stays, because other STE rules still block.
So the semicolon line is the only line this ruling removes.

## The outcome, and what protects it now

The semicolon line protected short, clear sentences. The STE sentence-length rule
(STE001) still blocks a long sentence, so the main harm a semicolon hides still has a gate.
