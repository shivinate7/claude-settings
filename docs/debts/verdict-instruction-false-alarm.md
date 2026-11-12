# A reviewer brief that asks for a verdict is refused

**What.** A reviewer brief line that lists the verdict choices is allowed: `verdict: PASS, FAIL or PARTIAL`,
`Verdict: PASS or FAIL` and `PASS/FAIL`. A line that names one verdict word is still refused as a prior verdict,
such as `Give a verdict: PASS.`, and so is a finding that quotes `verdict: FAIL` in backticks. The verdict-line
pattern matches `verdict` anywhere before a line's first colon, not at line start only.

**Where.** `hooks/guard.py`, `BRIEF_BLIND_VERDICT`, its first alternative `[^\n:]*?\bverdict\b`.

**Decision.** `reviewer-brief-blind`, a reviewer's brief holds no report or verdict.

**Retire.** Match the label at line start: `verdict`, or `prior`, `previous`, `last` or `earlier` before it,
and nothing else before the colon. Closed when red cases allow the one-word and backtick-quoted lines above and the
`Previous round verdict: FAIL` case stays refused.
