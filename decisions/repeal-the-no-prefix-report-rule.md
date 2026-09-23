# Repeal: prose above the report no longer needs a question

CLAUDE.md's Reports paragraph said:

> Put nothing above it, unless I asked a question that turn. Then answer
> above the report.

The owner repealed this sentence himself, in chat, after the measurement
below. This entry records his decision. It does not make one.

## The measurement

`lint/report_gate.py` blocks a reply that breaks the report shape.
`report_shape_ok(text, allow_prefix)` returned one boolean for two different
failures:

- A missing or malformed report. The owner got nothing usable. Blocking is
  right.
- A correct, complete report with a paragraph above it, on a turn with no
  question. The owner already had everything he needed. The block bought a
  deleted paragraph for the price of a full round trip.

Across 1,500 transcripts this gate blocked 32 times. All 32 resolved on the
next reply. None re-fired. It fired twice in one session on 2026-09-22, both
times on the second case above. The owner's own words: getting a reply an
extra time is the worst part of working this way.

## The outcome the old rule protected, and why it is not worth this cost

The rule's outcome was a report the owner could find fast, with no prose in
the way, on a turn with no question. That outcome is real.
But the gate's own history shows what it cost to protect: a full extra
reply, every time, for a report that was already correct. Thirty-two
blocks. Thirty-two round trips. None caught a report that was actually
missing or malformed. The rule spent the owner's time and bought nothing a
reader could not get by looking one blockquote further down.

## What still holds

The report itself is unchanged. It is still mandatory when a turn lands a
commit, a push, or a merge. It is still one blockquote. It still holds the
bold labels Done, Deviations, Input Needed, Next, in that order, dropping a
label that does not apply. It is still never a code fence, and nothing may
follow it. `lint/report_gate.py` still blocks a reply missing any of that,
no matter what sits above it. `report_shape_ok` no longer takes an
`allow_prefix` argument. The check it guarded is gone, not weakened. The
condition it depended on, "unless I asked a question", no longer exists.

## The mechanism

`lint/report_gate.py`, fixture-pinned by `lint/test_gates.py`'s
`ReportGateTests`. The anchor `reports-nothing-above-unless-question` is
retired. No rule in CLAUDE.md points at it. No row in
`lint/rule_mechanisms.json` names it any more.
